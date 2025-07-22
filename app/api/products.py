from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.db.repository import ProductRepository
from app.core.rag_service import RAGService
from app.models.schemas import Product, ProductCreate
from app.core.rate_limiter import PRODUCTS_RATE_LIMIT, limiter

router = APIRouter()


@router.get("/", response_model=List[Product])
@limiter.limit(PRODUCTS_RATE_LIMIT)
async def get_products(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get list of products (for testing)
    """
    repository = ProductRepository(db)
    products = repository.get_products(skip=skip, limit=limit)
    return products


@router.post("/", response_model=Product)
@limiter.limit(PRODUCTS_RATE_LIMIT)
async def create_product(
    request: Request,
    product: ProductCreate,
    db: Session = Depends(get_db)
):
    """
    Create new product with automatic embedding generation
    """
    try:
        repository = ProductRepository(db)
        rag_service = RAGService(repository)
        
        # Create product without embedding
        created_product = repository.create_product(product, [])
        
        # Generate embedding
        rag_service.add_product_embeddings(created_product.id)
        
        return created_product
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating product: {str(e)}")


@router.get("/{product_id}", response_model=Product)
@limiter.limit(PRODUCTS_RATE_LIMIT)
async def get_product(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db)
):
    """
    Get product by ID
    """
    repository = ProductRepository(db)
    product = repository.get_product(product_id)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product 