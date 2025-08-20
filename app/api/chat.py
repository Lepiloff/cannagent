from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.repository import StrainRepository
from app.core.rag_service import RAGService
from app.core.optimized_rag_service import OptimizedContextualRAGService
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
        # Create repository
        repository = StrainRepository(db)
        
        # Choose RAG service based on environment variable
        use_contextual_rag = os.getenv('USE_CONTEXTUAL_RAG', 'false').lower() == 'true'
        
        if use_contextual_rag:
            # Use new contextual RAG service
            rag_service = OptimizedContextualRAGService(repository)
            
            response = rag_service.process_contextual_query(
                query=chat_request.message,
                session_id=chat_request.session_id,
                history=chat_request.history,
                source_platform=chat_request.source_platform
            )
        else:
            # Use legacy RAG service for backwards compatibility
            rag_service = RAGService(repository)
            
            response = rag_service.process_query(
                query=chat_request.message,
                history=chat_request.history
            )
            
            # Add contextual fields for compatibility
            response.session_id = None
            response.query_type = "legacy"
            response.language = "es"  # Default
            response.confidence = 0.8
            response.is_restored = False
            response.is_fallback = False
        
        return response
        
    except Exception as e:
        import traceback
        print(f"Error processing request: {e}")
        print("Traceback:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}") 