from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
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


# New schemas for structured data
class FeelingBase(BaseModel):
    name: str = Field(..., description="Feeling name")
    energy_type: str = Field(..., description="Energy type: energizing, relaxing, or neutral")


class Feeling(FeelingBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}


class HelpsWithBase(BaseModel):
    name: str = Field(..., description="Medical condition or use")


class HelpsWith(HelpsWithBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}


class NegativeBase(BaseModel):
    name: str = Field(..., description="Negative side effect")


class Negative(NegativeBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}


class FlavorBase(BaseModel):
    name: str = Field(..., description="Flavor name")


class Flavor(FlavorBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}


class TerpeneBase(BaseModel):
    name: str = Field(..., description="Terpene name")
    description: Optional[str] = Field(None, description="Terpene description")


class Terpene(TerpeneBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}


class Strain(StrainBase):
    id: int
    url: Optional[str] = Field(None, description="Direct link to strain page on cannamente")
    created_at: datetime
    updated_at: datetime
    
    # Related data
    feelings: List[Feeling] = Field(default_factory=list, description="Strain feelings/effects")
    helps_with: List[HelpsWith] = Field(default_factory=list, description="Medical uses")
    negatives: List[Negative] = Field(default_factory=list, description="Side effects")
    flavors: List[Flavor] = Field(default_factory=list, description="Flavors")
    terpenes: List[Terpene] = Field(default_factory=list, description="Terpenes")
    
    model_config = {"from_attributes": True}


# Compact schemas for chat API responses (optimized for cannamente UI)
class CompactFeeling(BaseModel):
    name: str = Field(..., description="Feeling name")
    energy_type: Optional[str] = Field(None, description="Energy type: energizing, relaxing, or neutral")

class CompactHelpsWith(BaseModel):
    name: str = Field(..., description="Medical condition")

class CompactNegative(BaseModel):
    name: str = Field(..., description="Side effect")

class CompactFlavor(BaseModel):
    name: str = Field(..., description="Flavor name")

class CompactTerpene(BaseModel):
    """STAGE 2: Compact terpene schema for API responses"""
    name: str = Field(..., description="Terpene name")

class CompactStrain(BaseModel):
    """Optimized strain schema for chat API responses - excludes unnecessary fields"""
    id: int
    name: str = Field(..., description="Strain name")
    
    # Essential cannabinoid info
    cbd: Optional[Decimal] = Field(None, description="CBD percentage")
    thc: Optional[Decimal] = Field(None, description="THC percentage") 
    cbg: Optional[Decimal] = Field(None, description="CBG percentage")
    
    # Core classification
    category: Optional[str] = Field(None, description="Indica/Sativa/Hybrid")
    
    # Navigation & UI
    slug: Optional[str] = Field(None, description="URL slug")
    url: Optional[str] = Field(None, description="Direct strain page link")
    
    # Effects (compact - only essential fields)
    feelings: List[CompactFeeling] = Field(default_factory=list, description="Effects")
    helps_with: List[CompactHelpsWith] = Field(default_factory=list, description="Medical uses")
    negatives: List[CompactNegative] = Field(default_factory=list, description="Side effects")
    flavors: List[CompactFlavor] = Field(default_factory=list, description="Flavors")
    terpenes: List[CompactTerpene] = Field(default_factory=list, description="Terpenes (STAGE 2)")


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message") 
    history: Optional[List[str]] = Field(default=None, description="Message history")
    session_id: Optional[str] = Field(default=None, description="Session identifier for context continuity")
    source_platform: Optional[str] = Field(default=None, description="Source platform for analytics")


class ChatResponse(BaseModel):
    response: str = Field(..., description="AI response")
    recommended_strains: List[CompactStrain] = Field(default_factory=list, description="Recommended strains (optimized)")
    detected_intent: Optional[str] = Field(None, description="Detected user intent")
    filters_applied: Optional[dict] = Field(None, description="Applied filtering rules")
    
    # Enhanced context-aware fields
    session_id: Optional[str] = Field(None, description="Session identifier")
    query_type: Optional[str] = Field(None, description="Query type: new_search|follow_up|comparison|reset|clarification")
    language: Optional[str] = Field(None, description="Detected language (es/en)")
    confidence: Optional[float] = Field(None, description="Analysis confidence (0.0-1.0)")
    quick_actions: Optional[List[str]] = Field(None, description="Dynamic quick action suggestions")
    
    # Status indicators
    is_restored: bool = Field(default=False, description="Whether session was restored")
    is_fallback: bool = Field(default=False, description="Whether fallback analysis was used")
    warnings: Optional[List[str]] = Field(None, description="Any warnings or conflicts detected")
    
    
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


class StrainFilterRequest(BaseModel):
    """Request for filtered strain search"""
    query: Optional[str] = Field(None, description="Search query")
    categories: Optional[List[str]] = Field(None, description="Filter by categories")
    feelings: Optional[List[str]] = Field(None, description="Required feelings")
    helps_with: Optional[List[str]] = Field(None, description="Required medical uses")
    exclude_feelings: Optional[List[str]] = Field(None, description="Exclude feelings")
    min_thc: Optional[float] = Field(None, description="Minimum THC percentage")
    max_thc: Optional[float] = Field(None, description="Maximum THC percentage")
    min_cbd: Optional[float] = Field(None, description="Minimum CBD percentage")
    max_cbd: Optional[float] = Field(None, description="Maximum CBD percentage")
    limit: int = Field(10, description="Maximum results to return") 