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

strain_other_terpenes_table = Table(
    'strains_strain_other_terpenes',  # Django M2M table
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('strain_id', Integer, ForeignKey('strains_strain.id', ondelete='CASCADE')),
    Column('terpene_id', Integer, ForeignKey('strains_terpene.id', ondelete='CASCADE'))
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
    dominant_terpene_id = Column(Integer, ForeignKey('strains_terpene.id', ondelete='SET NULL'), nullable=True)

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
    dominant_terpene = relationship(
        'Terpene',
        foreign_keys=[dominant_terpene_id],
        back_populates='dominant_in_strains',
    )
    other_terpenes = relationship(
        'Terpene',
        secondary=strain_other_terpenes_table,
        back_populates='in_strains',
    )

    @property
    def terpenes(self):
        """Combined terpene list matching the API's legacy response shape."""
        combined = []
        seen_ids = set()
        for terpene in [self.dominant_terpene] + list(self.other_terpenes or []):
            if not terpene:
                continue
            marker = terpene.id if terpene.id is not None else id(terpene)
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            combined.append(terpene)
        return combined
    
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
    # Energy type for taxonomy (e.g., energizing, relaxing, neutral)
    energy_type = Column(String(20), nullable=True)
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
    dominant_in_strains = relationship(
        'Strain',
        foreign_keys='Strain.dominant_terpene_id',
        back_populates='dominant_terpene',
    )
    in_strains = relationship(
        'Strain',
        secondary=strain_other_terpenes_table,
        back_populates='other_terpenes',
    )

    @property
    def strains(self):
        """Combined strain list for callers that still expect Terpene.strains."""
        combined = []
        seen_ids = set()
        for strain in list(self.dominant_in_strains or []) + list(self.in_strains or []):
            marker = strain.id if strain.id is not None else id(strain)
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            combined.append(strain)
        return combined

    def __repr__(self):
        return f"<Terpene(id={self.id}, name='{self.name}')>" 
