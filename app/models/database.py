from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Numeric, ForeignKey, Table
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import os

Base = declarative_base()


# Association tables for many-to-many relationships (Django table names)
strain_feelings_table = Table(
    'strains_strain_feelings',  # Django M2M table
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('feeling_id', Integer, ForeignKey('strains_feeling.id', ondelete='CASCADE'))
)

strain_helps_with_table = Table(
    'strains_strain_helps_with',  # Django M2M table
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('helpswith_id', Integer, ForeignKey('strains_helpswith.id', ondelete='CASCADE'))
)

strain_negatives_table = Table(
    'strains_strain_negatives',  # Django M2M table
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('negative_id', Integer, ForeignKey('strains_negative.id', ondelete='CASCADE'))
)

strain_flavors_table = Table(
    'strains_strain_flavors',  # Django M2M table
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('flavor_id', Integer, ForeignKey('strains_flavor.id', ondelete='CASCADE'))
)

strain_terpenes_table = Table(
    'strains_strain_terpenes',  # Django M2M table
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('terpene_id', Integer, ForeignKey('strains_terpene.id', ondelete='CASCADE')),
    Column('is_dominant', Boolean, default=False)
)


class Strain(Base):
    """Strain model matching cannamente Django structure with vector representation"""
    __tablename__ = "strains_strain"  # Django table name

    id = Column(Integer, primary_key=True, index=True)

    # Legacy fields (for backward compatibility)
    name = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    text_content = Column(Text, nullable=True)  # HTMLField equivalent
    description = Column(Text, nullable=True)
    keywords = Column(String(255), nullable=True)

    # Multilingual content fields (NEW)
    title_en = Column(String(255), nullable=True)
    title_es = Column(String(255), nullable=True)
    description_en = Column(Text, nullable=True)
    description_es = Column(Text, nullable=True)
    text_content_en = Column(Text, nullable=True)
    text_content_es = Column(Text, nullable=True)
    keywords_en = Column(String(255), nullable=True)
    keywords_es = Column(String(255), nullable=True)

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

    # Vector embeddings for semantic search (multilingual support)
    embedding_en = Column(Vector(int(os.getenv('VECTOR_DIMENSION', '1536'))), nullable=True)
    embedding_es = Column(Vector(int(os.getenv('VECTOR_DIMENSION', '1536'))), nullable=True)
    
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
    __tablename__ = "strains_feeling"  # Django table name

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    # Multilingual fields from cannamente
    name_en = Column(String(50), nullable=True)
    name_es = Column(String(50), nullable=True)

    # Relationships
    strains = relationship('Strain', secondary=strain_feelings_table, back_populates='feelings')

    def __repr__(self):
        return f"<Feeling(id={self.id}, name='{self.name}')>"


class HelpsWith(Base):
    """Medical conditions/uses that strains help with"""
    __tablename__ = "strains_helpswith"  # Django table name

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    # Multilingual fields from cannamente
    name_en = Column(String(100), nullable=True)
    name_es = Column(String(100), nullable=True)

    # Relationships
    strains = relationship('Strain', secondary=strain_helps_with_table, back_populates='helps_with')

    def __repr__(self):
        return f"<HelpsWith(id={self.id}, name='{self.name}')>"


class Negative(Base):
    """Negative side effects"""
    __tablename__ = "strains_negative"  # Django table name

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    # Multilingual fields from cannamente
    name_en = Column(String(50), nullable=True)
    name_es = Column(String(50), nullable=True)

    # Relationships
    strains = relationship('Strain', secondary=strain_negatives_table, back_populates='negatives')

    def __repr__(self):
        return f"<Negative(id={self.id}, name='{self.name}')>"


class Flavor(Base):
    """Strain flavors and taste profiles"""
    __tablename__ = "strains_flavor"  # Django table name

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    # Multilingual fields from cannamente
    name_en = Column(String(50), nullable=True)
    name_es = Column(String(50), nullable=True)

    # Relationships
    strains = relationship('Strain', secondary=strain_flavors_table, back_populates='flavors')

    def __repr__(self):
        return f"<Flavor(id={self.id}, name='{self.name}')>"


class Terpene(Base):
    """Terpenes found in strains"""
    __tablename__ = "strains_terpene"  # Django table name

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)  # Scientific name
    description = Column(Text, nullable=False)  # Required in cannamente
    # Multilingual descriptions from cannamente
    description_en = Column(Text, nullable=True)
    description_es = Column(Text, nullable=True)
    # Translation fields from cannamente
    last_translated_at = Column(DateTime, nullable=True)
    translation_error = Column(Text, nullable=True)
    translation_source_hash = Column(String(255), nullable=True)
    translation_status = Column(String(50), nullable=False)  # Required in cannamente

    # Relationships
    strains = relationship('Strain', secondary=strain_terpenes_table, back_populates='terpenes')

    def __repr__(self):
        return f"<Terpene(id={self.id}, name='{self.name}')>" 