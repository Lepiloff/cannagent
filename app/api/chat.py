from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.repository import StrainRepository
from app.core.rag_service import RAGService
from app.models.schemas import ChatRequest, ChatResponse
from app.core.rate_limiter import CHAT_RATE_LIMIT, limiter

router = APIRouter()


@router.post("/ask/", response_model=ChatResponse)
@limiter.limit(CHAT_RATE_LIMIT)
async def ask_question(
    request: Request,
    chat_request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Process user question using RAG
    """
    try:
        # Create repository and RAG service
        repository = StrainRepository(db)
        rag_service = RAGService(repository)
        
        # Process request
        response = rag_service.process_query(
            query=chat_request.message,
            history=chat_request.history
        )
        
        return response
        
    except Exception as e:
        import traceback
        print(f"Error processing request: {e}")
        print("Traceback:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}") 