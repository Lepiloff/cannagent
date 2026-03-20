import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from slowapi.util import get_remote_address

from app.core.smart_rag_service import SmartRAGService
from app.core.session_manager import SessionLockTimeout
from app.models.schemas import ChatRequest, ChatResponse
from app.core.rate_limiter import CHAT_RATE_LIMIT, limiter
from app.core.input_sanitizer import sanitize_input, detect_prompt_injection
from app.core.metrics import record_pi_detection

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ask/", response_model=ChatResponse)
@limiter.limit(CHAT_RATE_LIMIT)
async def ask_question(
    request: Request,
    chat_request: ChatRequest,
):
    """
    Process user question using Context-Aware RAG
    """
    try:
        # Log language/locale signals (helps debug why language defaults to 'es')
        raw_body_language = None
        raw_body_keys = None
        try:
            raw_body = await request.json()
            if isinstance(raw_body, dict):
                raw_body_language = raw_body.get("language")
                raw_body_keys = sorted(raw_body.keys())
        except Exception:
            # Don't fail request if body can't be parsed (FastAPI already parsed `chat_request`)
            pass

        logger.info(
            "Chat request locale: parsed.language=%r body.language=%r accept-language=%r body.keys=%s",
            chat_request.language,
            raw_body_language,
            request.headers.get("accept-language"),
            raw_body_keys,
        )

        # Sanitize user input before pipeline
        clean_message = sanitize_input(chat_request.message)
        client_ip = get_remote_address(request)

        # Prompt injection detection — log only, let pipeline handle via prompt hardening
        if detect_prompt_injection(clean_message):
            logger.warning(
                "PI signal: endpoint=ask session=%s ip=%s msg=%s",
                chat_request.session_id, client_ip, clean_message[:120],
            )
            record_pi_detection("ask")

        # Granular async pipeline: LLM calls run as native async on event loop,
        # DB calls run in a dedicated per-request thread executor.
        rag_service = SmartRAGService(repository=None)
        response = await rag_service.aprocess_contextual_query(
            query=clean_message,
            session_id=chat_request.session_id,
            language=chat_request.language,
            history=chat_request.history,
            source_platform=chat_request.source_platform,
        )

        # Output leakage is checked inside SmartRAGService._build_streamlined_response
        # and _update_session_streamlined — no duplicate check needed here.

        return response

    except SessionLockTimeout:
        raise HTTPException(
            status_code=503,
            detail="Session is busy processing another request. Please retry shortly.",
        )
    except Exception as e:
        import traceback
        print(f"Error processing request: {e}")
        print("Traceback:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")


@router.post("/ask/stream")
@limiter.limit(CHAT_RATE_LIMIT)
async def ask_question_stream(
    request: Request,
    chat_request: ChatRequest,
):
    """
    Streaming version of /ask/ endpoint.

    Returns Server-Sent Events (SSE):
    - First event: {"type": "metadata", "data": {...}} with strains, filters, session_id
    - Subsequent events: {"type": "response_chunk", "text": "..."} with streaming text
    - Final event: {"type": "done"}

    The metadata is sent as soon as strain search completes (~4s),
    then the natural language response streams token-by-token.
    This reduces perceived latency from ~7s to ~4s for first meaningful content.
    """
    clean_message = sanitize_input(chat_request.message)
    client_ip = get_remote_address(request)

    # Prompt injection detection — log only, let pipeline handle via prompt hardening
    if detect_prompt_injection(clean_message):
        logger.warning(
            "PI signal: endpoint=stream session=%s ip=%s msg=%s",
            chat_request.session_id, client_ip, clean_message[:120],
        )
        record_pi_detection("stream")

    async def event_generator():
        try:
            rag_service = SmartRAGService(repository=None)
            async for chunk in rag_service.aprocess_contextual_query_streaming(
                query=clean_message,
                session_id=chat_request.session_id,
                language=chat_request.language,
                history=chat_request.history,
                source_platform=chat_request.source_platform,
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except SessionLockTimeout:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Session busy'})}\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
