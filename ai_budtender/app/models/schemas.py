from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ProductBase(BaseModel):
    name: str = Field(..., description="Product name")
    description: str = Field(..., description="Product description")


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    history: Optional[List[str]] = Field(default=None, description="Message history")


class ChatResponse(BaseModel):
    response: str = Field(..., description="AI response")
    recommended_products: List[Product] = Field(default_factory=list, description="Recommended products")
    
    
class HealthResponse(BaseModel):
    status: str = Field(..., description="System status")
    database: str = Field(..., description="Database status")
    redis: Optional[str] = Field(default=None, description="Redis cache status")
    timestamp: datetime = Field(..., description="Check timestamp")


class CacheStatsResponse(BaseModel):
    status: str = Field(..., description="Cache status")
    host: str = Field(..., description="Redis host")
    port: int = Field(..., description="Redis port")
    db: int = Field(..., description="Redis database")
    
    
class MetricsResponse(BaseModel):
    total_requests: int = Field(..., description="Total HTTP requests")
    active_requests: int = Field(..., description="Active HTTP requests")
    total_chat_requests: int = Field(..., description="Total chat requests")
    total_embeddings: int = Field(..., description="Total embedding requests")
    cache_hit_rate: float = Field(..., description="Cache hit rate percentage") 