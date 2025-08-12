from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Numeric, ForeignKey, Table
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import os

Base = declarative_base()


# Association tables for many-to-many relationships
strain_feelings_table = Table(
    'strain_feelings',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('feeling_id', Integer, ForeignKey('feelings.id', ondelete='CASCADE'))
)

strain_helps_with_table = Table(
    'strain_helps_with',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('helps_with_id', Integer, ForeignKey('helps_with.id', ondelete='CASCADE'))
)

strain_negatives_table = Table(
    'strain_negatives',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('negative_id', Integer, ForeignKey('negatives.id', ondelete='CASCADE'))
)

strain_flavors_table = Table(
    'strain_flavors',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('flavor_id', Integer, ForeignKey('flavors.id', ondelete='CASCADE'))
)

strain_terpenes_table = Table(
    'strain_terpenes',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('terpene_id', Integer, ForeignKey('terpenes.id', ondelete='CASCADE')),
    Column('is_dominant', Boolean, default=False)
)


class Strain(Base):
    """Strain model matching cannamente Django structure with vector representation"""
    __tablename__ = "strains_strain"  # Django table name
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    text_content = Column(Text, nullable=True)  # HTMLField equivalent
    description = Column(Text, nullable=True)
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
    embedding = Column(Vector(int(os.getenv('VECTOR_DIMENSION', '1536'))), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    feelings = relationship('Feeling', secondary=strain_feelings_table, back_populates='strains')
    helps_with = relationship('HelpsWith', secondary=strain_helps_with_table, back_populates='strains')
    negatives = relationship('Negative', secondary=strain_negatives_table, back_populates='strains')
    flavors = relationship('Flavor', secondary=strain_flavors_table, back_populates='strains')
    terpenes = relationship('Terpene', secondary=strain_terpenes_table, back_populates='strains')
    
    def __repr__(self):
        return f"<Strain(id={self.id}, name='{self.name}', category='{self.category}')>"


# Keep the old Product model for backward compatibility
class Product(Base):
    """Legacy Product model - kept for compatibility"""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    embedding = Column(Vector(int(os.getenv('VECTOR_DIMENSION', '1536'))), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    
    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.name}')>"


# New models for structured strain data
class Feeling(Base):
    """Strain feelings/effects (e.g., Relaxed, Energetic, Creative)"""
    __tablename__ = "feelings"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    energy_type = Column(String(20), nullable=False)  # energizing, relaxing, neutral
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    strains = relationship('Strain', secondary=strain_feelings_table, back_populates='feelings')
    
    def __repr__(self):
        return f"<Feeling(id={self.id}, name='{self.name}', energy_type='{self.energy_type}')>"


class HelpsWith(Base):
    """Medical conditions/uses that strains help with"""
    __tablename__ = "helps_with"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    strains = relationship('Strain', secondary=strain_helps_with_table, back_populates='helps_with')
    
    def __repr__(self):
        return f"<HelpsWith(id={self.id}, name='{self.name}')>"


class Negative(Base):
    """Negative side effects"""
    __tablename__ = "negatives"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    strains = relationship('Strain', secondary=strain_negatives_table, back_populates='negatives')
    
    def __repr__(self):
        return f"<Negative(id={self.id}, name='{self.name}')>"


class Flavor(Base):
    """Strain flavors and taste profiles"""
    __tablename__ = "flavors"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    strains = relationship('Strain', secondary=strain_flavors_table, back_populates='flavors')
    
    def __repr__(self):
        return f"<Flavor(id={self.id}, name='{self.name}')>"


class Terpene(Base):
    """Terpenes found in strains"""
    __tablename__ = "terpenes"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    strains = relationship('Strain', secondary=strain_terpenes_table, back_populates='terpenes')
    
    def __repr__(self):
        return f"<Terpene(id={self.id}, name='{self.name}')>" 