import logging

from fastapi import APIRouter, HTTPException, Request
from app.core.smart_rag_service import SmartRAGService
from app.core.session_manager import SessionLockTimeout
from app.models.schemas import ChatRequest, ChatResponse
from app.core.rate_limiter import CHAT_RATE_LIMIT, limiter

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

        # Granular async pipeline: LLM calls run as native async on event loop,
        # DB calls run in a dedicated per-request thread executor.
        rag_service = SmartRAGService(repository=None)
        response = await rag_service.aprocess_contextual_query(
            query=chat_request.message,
            session_id=chat_request.session_id,
            language=chat_request.language,
            history=chat_request.history,
            source_platform=chat_request.source_platform,
        )
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
