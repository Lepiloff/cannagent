from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.repository import StrainRepository
from app.core.smart_rag_service import SmartRAGService
from app.models.schemas import ChatRequest, ChatResponse
from app.core.rate_limiter import CHAT_RATE_LIMIT, limiter
import os

router = APIRouter()


@router.post("/ask/", response_model=ChatResponse)
@limiter.limit(CHAT_RATE_LIMIT)
async def ask_question(
    request: Request,
    chat_request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Process user question using Context-Aware RAG
    """
    try:
        # Always use Smart Query Executor v3.0 (simplified architecture)
        repository = StrainRepository(db)
        rag_service = SmartRAGService(repository)
        
        response = rag_service.process_contextual_query(
            query=chat_request.message,
            session_id=chat_request.session_id,
            language=chat_request.language,
            history=chat_request.history,
            source_platform=chat_request.source_platform
        )
        
        return response
        
    except Exception as e:
        import traceback
        print(f"Error processing request: {e}")
        print("Traceback:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}") 