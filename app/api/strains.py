from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.db.repository import StrainRepository
from app.models.schemas import Strain
from app.core.rate_limiter import PRODUCTS_RATE_LIMIT, limiter
from app.config import settings

router = APIRouter()


@router.get("/", response_model=List[Strain])
@limiter.limit(PRODUCTS_RATE_LIMIT)
async def get_strains(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    Get list of available strains
    """
    try:
        repository = StrainRepository(db)
        strains = repository.get_strains(skip=skip, limit=limit)
        
        # Convert to response format with URLs
        result = []
        for strain in strains:
            strain_url = None
            if strain.slug:
                strain_url = f"{settings.cannamente_base_url}{settings.strain_url_pattern.format(slug=strain.slug)}"
            
            result.append(Strain(
                id=strain.id,
                name=strain.name,
                title=strain.title,
                description=strain.description,
                text_content=strain.text_content,
                keywords=strain.keywords,
                cbd=strain.cbd,
                thc=strain.thc,
                cbg=strain.cbg,
                rating=strain.rating,
                category=strain.category,
                img=strain.img,
                img_alt_text=strain.img_alt_text,
                active=strain.active,
                top=strain.top,
                main=strain.main,
                is_review=strain.is_review,
                slug=strain.slug,
                url=strain_url,
                created_at=strain.created_at,
                updated_at=strain.updated_at
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving strains: {str(e)}")


@router.get("/{strain_id}", response_model=Strain)
@limiter.limit(PRODUCTS_RATE_LIMIT)
async def get_strain(
    request: Request,
    strain_id: int,
    db: Session = Depends(get_db)
):
    """
    Get specific strain by ID
    """
    try:
        repository = StrainRepository(db)
        strain = repository.get_strain(strain_id)
        
        if not strain:
            raise HTTPException(status_code=404, detail="Strain not found")
        
        # Build URL
        strain_url = None
        if strain.slug:
            strain_url = f"{settings.cannamente_base_url}{settings.strain_url_pattern.format(slug=strain.slug)}"
        
        return Strain(
            id=strain.id,
            name=strain.name,
            title=strain.title,
            description=strain.description,
            text_content=strain.text_content,
            keywords=strain.keywords,
            cbd=strain.cbd,
            thc=strain.thc,
            cbg=strain.cbg,
            rating=strain.rating,
            category=strain.category,
            img=strain.img,
            img_alt_text=strain.img_alt_text,
            active=strain.active,
            top=strain.top,
            main=strain.main,
            is_review=strain.is_review,
            slug=strain.slug,
            url=strain_url,
            created_at=strain.created_at,
            updated_at=strain.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving strain: {str(e)}")
