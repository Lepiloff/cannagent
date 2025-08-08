from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Numeric, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.config import settings

Base = declarative_base()


class Strain(Base):
    """Strain model matching cannamente Django structure with vector representation"""
    __tablename__ = "strains_strain"  # Django table name
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    text_content = Column(Text, nullable=True)  # HTMLField equivalent
    description = Column(String(255), nullable=True)
    keywords = Column(String(255), nullable=True)
    
    # Cannabinoid content
    cbd = Column(Numeric(5, 2), nullable=True)
    thc = Column(Numeric(5, 2), nullable=True)
    cbg = Column(Numeric(5, 2), nullable=True)
    
    # Rating and category
    rating = Column(Numeric(3, 1), nullable=True)
    category = Column(String(10), nullable=True)  # Hybrid, Sativa, Indica
    
    # Image fields
    img = Column(String(255), nullable=True)  # Image path
    img_alt_text = Column(String(255), nullable=True)
    
    # Flags
    active = Column(Boolean, default=False)
    top = Column(Boolean, default=False)
    main = Column(Boolean, default=False)
    is_review = Column(Boolean, default=False)
    
    # Slug for URL
    slug = Column(String(255), unique=True, nullable=True)
    
    # Vector embedding for semantic search
    embedding = Column(Vector(settings.vector_dimension), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Strain(id={self.id}, name='{self.name}', category='{self.category}')>"


# Keep the old Product model for backward compatibility
class Product(Base):
    """Legacy Product model - kept for compatibility"""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    embedding = Column(Vector(settings.vector_dimension), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    
    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.name}')>" 