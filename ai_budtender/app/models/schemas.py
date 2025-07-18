from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from decimal import Decimal


class StrainBase(BaseModel):
    name: str = Field(..., description="Strain name")
    title: Optional[str] = Field(None, description="Strain title")
    description: Optional[str] = Field(None, description="Strain description")
    text_content: Optional[str] = Field(None, description="Strain content")
    keywords: Optional[str] = Field(None, description="SEO keywords")
    
    # Cannabinoid content
    cbd: Optional[Decimal] = Field(None, description="CBD content percentage")
    thc: Optional[Decimal] = Field(None, description="THC content percentage")
    cbg: Optional[Decimal] = Field(None, description="CBG content percentage")
    
    # Rating and category
    rating: Optional[Decimal] = Field(None, description="Strain rating")
    category: Optional[str] = Field(None, description="Strain category (Hybrid/Sativa/Indica)")
    
    # Image fields
    img: Optional[str] = Field(None, description="Image path")
    img_alt_text: Optional[str] = Field(None, description="Image alt text")
    
    # Flags
    active: bool = Field(False, description="Is strain active")
    top: bool = Field(False, description="Is top strain")
    main: bool = Field(False, description="Is main strain")
    is_review: bool = Field(False, description="Is review strain")
    
    # Slug
    slug: Optional[str] = Field(None, description="URL slug")


class StrainCreate(StrainBase):
    pass


class Strain(StrainBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Legacy Product schemas for backward compatibility
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
    recommended_strains: List[Strain] = Field(default_factory=list, description="Recommended strains")
    recommended_products: List[Product] = Field(default_factory=list, description="Legacy recommended products")
    
    
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