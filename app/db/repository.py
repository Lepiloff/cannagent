from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Set, Dict, Any
from app.models.database import (
    Strain as StrainModel, 
    Feeling, 
    HelpsWith, 
    Negative, 
    Flavor, 
    Terpene
)
from app.models.schemas import StrainCreate, StrainFilterRequest
from pgvector.sqlalchemy import Vector
from sqlalchemy import text, and_, or_, not_
from app.core.intent_detection import IntentType, IntentDetector


class StrainRepository:
    """Enhanced repository for strain operations with structured filtering"""
    
    def __init__(self, db: Session):
        self.db = db
        self.intent_detector = IntentDetector()
    def get_strain(self, strain_id: int) -> Optional[StrainModel]:
        """Получение штамма по ID"""
        return self.db.query(StrainModel).filter(StrainModel.id == strain_id).first()
    
    def get_strains(self, skip: int = 0, limit: int = 100) -> List[StrainModel]:
        """Получение списка штаммов"""
        return self.db.query(StrainModel).filter(StrainModel.active == True).offset(skip).limit(limit).all()
    
    def search_similar_strains(self, query_embedding: List[float], limit: int = 5) -> List[StrainModel]:
        """Legacy vector similarity search (use search_strains_with_intent for better results)"""
        return (
            self.db.query(StrainModel)
            .options(joinedload(StrainModel.feelings))
            .options(joinedload(StrainModel.helps_with))
            .options(joinedload(StrainModel.negatives))
            .options(joinedload(StrainModel.flavors))
            .filter(StrainModel.embedding.isnot(None))
            .filter(StrainModel.active == True)
            .order_by(StrainModel.embedding.cosine_distance(query_embedding))
            .limit(limit)
            .all()
        )
    
    def search_strains_with_intent(self, query: str, query_embedding: Optional[List[float]] = None, 
                                  limit: int = 5) -> List[StrainModel]:
        """Smart strain search with intent detection and structured filtering"""
        
        # Detect user intent
        intent = self.intent_detector.detect_intent(query)
        filters = self.intent_detector.get_intent_filters(intent)
        
        print(f"🔍 SEARCH DEBUG: Query='{query}', Intent={intent.value}, Limit={limit}")
        print(f"🔍 SEARCH DEBUG: Filters={filters}")
        
        results = self._apply_structured_search(
            query_embedding=query_embedding,
            required_feelings=filters.get("required_feelings", set()),
            preferred_categories=filters.get("preferred_categories", set()),
            exclude_feelings=filters.get("exclude_feelings", set()),
            required_helps_with=filters.get("required_helps_with", set()),
            exclude_helps_with=filters.get("exclude_helps_with", set()),
            limit=limit
        )
        
        print(f"🔍 SEARCH DEBUG: Found {len(results)} strains: {[s.name for s in results]}")
        return results
    
    def _apply_structured_search(self, query_embedding: Optional[List[float]] = None,
                               required_feelings: Set[str] = None,
                               preferred_categories: Set[str] = None,
                               exclude_feelings: Set[str] = None,
                               required_helps_with: Set[str] = None,
                               exclude_helps_with: Set[str] = None,
                               limit: int = 5) -> List[StrainModel]:
        """Apply structured filtering with optional vector similarity"""
        
        print(f"🔍 DB DEBUG: Starting search with limit={limit}")
        
        base_query = (
            self.db.query(StrainModel)
            .options(joinedload(StrainModel.feelings))
            .options(joinedload(StrainModel.helps_with))
            .options(joinedload(StrainModel.negatives))
            .options(joinedload(StrainModel.flavors))
            .filter(StrainModel.active == True)
        )
        
        # Check total count before filtering
        total_before = base_query.count()
        print(f"🔍 DB DEBUG: Total active strains before filtering: {total_before}")
        
        # Apply category filtering (preferred categories)
        if preferred_categories:
            base_query = base_query.filter(StrainModel.category.in_(list(preferred_categories)))
            after_categories = base_query.count()
            print(f"🔍 DB DEBUG: After category filtering ({preferred_categories}): {after_categories}")
        
        # Apply required feelings filtering (OR logic - any of these feelings is good)
        # Use subquery approach to avoid DISTINCT/ORDER BY conflict
        if required_feelings:
            feeling_strain_ids = (
                self.db.query(StrainModel.id)
                .join(StrainModel.feelings)
                .filter(Feeling.name.in_(list(required_feelings)))
                .distinct()
            ).subquery()
            
            base_query = base_query.filter(StrainModel.id.in_(
                self.db.query(feeling_strain_ids.c.id)
            ))
            after_feelings = base_query.count()
            print(f"🔍 DB DEBUG: After required feelings filtering ({required_feelings}): {after_feelings}")
        
        # Apply helps_with filtering (optional - just prefer these)
        # Don't make this mandatory for now to avoid SQL complexity
        
        # Apply exclude feelings filtering
        if exclude_feelings:
            for feeling in exclude_feelings:
                before_exclude = base_query.count()
                subquery = (
                    self.db.query(StrainModel.id)
                    .join(StrainModel.feelings)
                    .filter(Feeling.name == feeling)
                )
                base_query = base_query.filter(~StrainModel.id.in_(subquery))
                after_exclude = base_query.count()
                print(f"🔍 DB DEBUG: After excluding feeling '{feeling}': {before_exclude} -> {after_exclude}")
        
        # Apply exclude helps_with filtering
        if exclude_helps_with:
            for condition in exclude_helps_with:
                before_exclude = base_query.count()
                subquery = (
                    self.db.query(StrainModel.id)
                    .join(StrainModel.helps_with)
                    .filter(HelpsWith.name == condition)
                )
                base_query = base_query.filter(~StrainModel.id.in_(subquery))
                after_exclude = base_query.count()
                print(f"🔍 DB DEBUG: After excluding helps_with '{condition}': {before_exclude} -> {after_exclude}")
        
        # Apply vector similarity if embedding provided
        if query_embedding:
            base_query = (
                base_query
                .filter(StrainModel.embedding.isnot(None))
                .order_by(StrainModel.embedding.cosine_distance(query_embedding))
            )
            with_embedding = base_query.count()
            print(f"🔍 DB DEBUG: After embedding filter: {with_embedding}")
        else:
            # Default ordering by name if no vector search
            base_query = base_query.order_by(StrainModel.name)
            print(f"🔍 DB DEBUG: No embedding, using name ordering")
        
        final_results = base_query.limit(limit).all()
        print(f"🔍 DB DEBUG: Final results after limit({limit}): {len(final_results)} strains")
        
        return final_results
    
    def filter_strains_advanced(self, filter_request: StrainFilterRequest) -> List[StrainModel]:
        """Advanced strain filtering with multiple criteria"""
        
        base_query = (
            self.db.query(StrainModel)
            .options(joinedload(StrainModel.feelings))
            .options(joinedload(StrainModel.helps_with))
            .options(joinedload(StrainModel.negatives))
            .options(joinedload(StrainModel.flavors))
            .filter(StrainModel.active == True)
        )
        
        # Category filtering
        if filter_request.categories:
            base_query = base_query.filter(StrainModel.category.in_(filter_request.categories))
        
        # THC range filtering
        if filter_request.min_thc is not None:
            base_query = base_query.filter(StrainModel.thc >= filter_request.min_thc)
        if filter_request.max_thc is not None:
            base_query = base_query.filter(StrainModel.thc <= filter_request.max_thc)
        
        # CBD range filtering
        if filter_request.min_cbd is not None:
            base_query = base_query.filter(StrainModel.cbd >= filter_request.min_cbd)
        if filter_request.max_cbd is not None:
            base_query = base_query.filter(StrainModel.cbd <= filter_request.max_cbd)
        
        # Feelings filtering - use subquery approach to avoid DISTINCT conflicts
        if filter_request.feelings:
            for feeling in filter_request.feelings:
                feeling_strain_ids = (
                    self.db.query(StrainModel.id)
                    .join(StrainModel.feelings)
                    .filter(Feeling.name == feeling)
                ).subquery()
                
                base_query = base_query.filter(StrainModel.id.in_(
                    self.db.query(feeling_strain_ids.c.id)
                ))
        
        # Helps with filtering - use subquery approach to avoid DISTINCT conflicts
        if filter_request.helps_with:
            for condition in filter_request.helps_with:
                helps_strain_ids = (
                    self.db.query(StrainModel.id)
                    .join(StrainModel.helps_with)
                    .filter(HelpsWith.name == condition)
                ).subquery()
                
                base_query = base_query.filter(StrainModel.id.in_(
                    self.db.query(helps_strain_ids.c.id)
                ))
        
        # Exclude feelings
        if filter_request.exclude_feelings:
            for feeling in filter_request.exclude_feelings:
                subquery = (
                    self.db.query(StrainModel.id)
                    .join(StrainModel.feelings)
                    .filter(Feeling.name == feeling)
                )
                base_query = base_query.filter(~StrainModel.id.in_(subquery))
        
        return base_query.limit(filter_request.limit).all()
    
    def update_strain_embedding(self, strain_id: int, embedding: List[float]) -> Optional[StrainModel]:
        """Обновление эмбеддинга штамма"""
        strain = self.get_strain(strain_id)
        if strain:
            strain.embedding = embedding
            self.db.commit()
            self.db.refresh(strain)
        return strain
    
    def get_strain_with_relations(self, strain_id: int) -> Optional[StrainModel]:
        """Get strain with all related data loaded"""
        return (
            self.db.query(StrainModel)
            .options(joinedload(StrainModel.feelings))
            .options(joinedload(StrainModel.helps_with))
            .options(joinedload(StrainModel.negatives))
            .options(joinedload(StrainModel.flavors))
            .options(joinedload(StrainModel.terpenes))
            .filter(StrainModel.id == strain_id)
            .first()
        )
    
    def get_strains_with_relations(self, skip: int = 0, limit: int = 100) -> List[StrainModel]:
        """Get strains list with all relations loaded"""
        return (
            self.db.query(StrainModel)
            .options(joinedload(StrainModel.feelings))
            .options(joinedload(StrainModel.helps_with))
            .options(joinedload(StrainModel.negatives))
            .options(joinedload(StrainModel.flavors))
            .filter(StrainModel.active == True)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    # Helper methods for managing reference data
    def get_all_feelings(self) -> List[Feeling]:
        """Get all available feelings"""
        return self.db.query(Feeling).order_by(Feeling.name).all()
    
    def get_all_helps_with(self) -> List[HelpsWith]:
        """Get all available medical conditions"""
        return self.db.query(HelpsWith).order_by(HelpsWith.name).all()
    
    def get_all_negatives(self) -> List[Negative]:
        """Get all negative effects"""
        return self.db.query(Negative).order_by(Negative.name).all()
    
    def get_all_flavors(self) -> List[Flavor]:
        """Get all flavors"""
        return self.db.query(Flavor).order_by(Flavor.name).all()
    
    def create_or_get_feeling(self, name: str, energy_type: str) -> Feeling:
        """Create or get existing feeling"""
        feeling = self.db.query(Feeling).filter(Feeling.name == name).first()
        if not feeling:
            feeling = Feeling(name=name, energy_type=energy_type)
            self.db.add(feeling)
            self.db.commit()
            self.db.refresh(feeling)
        return feeling
    
    def create_or_get_helps_with(self, name: str) -> HelpsWith:
        """Create or get existing helps_with condition"""
        condition = self.db.query(HelpsWith).filter(HelpsWith.name == name).first()
        if not condition:
            condition = HelpsWith(name=name)
            self.db.add(condition)
            self.db.commit()
            self.db.refresh(condition)
        return condition
    
    def create_strain(self, strain_data: dict, embedding: Optional[List[float]] = None) -> StrainModel:
        """Создание нового штамма с эмбеддингом"""
        db_strain = StrainModel(
            name=strain_data["name"],
            title=strain_data.get("title"),
            description=strain_data.get("description"),
            text_content=strain_data.get("text_content"),
            keywords=strain_data.get("keywords"),
            cbd=strain_data.get("cbd"),
            thc=strain_data.get("thc"),
            cbg=strain_data.get("cbg"),
            rating=strain_data.get("rating"),
            category=strain_data.get("category"),
            img=strain_data.get("img"),
            img_alt_text=strain_data.get("img_alt_text"),
            active=strain_data.get("active", True),
            top=strain_data.get("top", False),
            main=strain_data.get("main", False),
            is_review=strain_data.get("is_review", False),
            slug=strain_data.get("slug"),
            embedding=embedding
        )
        self.db.add(db_strain)
        self.db.commit()
        self.db.refresh(db_strain)
        return db_strain
    
    def update_strain_relations(self, strain: StrainModel, 
                              feelings: List[str] = None,
                              helps_with: List[str] = None,
                              negatives: List[str] = None,
                              flavors: List[str] = None) -> StrainModel:
        """Update strain relations from cannamente data"""
        
        # Update feelings
        if feelings:
            strain.feelings.clear()
            for feeling_name in feelings:
                # Determine energy type based on predefined mapping
                from app.core.intent_detection import get_energy_type
                energy_type = get_energy_type(feeling_name)
                if energy_type:
                    feeling = self.create_or_get_feeling(feeling_name, energy_type.value)
                    strain.feelings.append(feeling)
        
        # Update helps_with
        if helps_with:
            strain.helps_with.clear()
            for condition_name in helps_with:
                condition = self.create_or_get_helps_with(condition_name)
                strain.helps_with.append(condition)
        
        # Update negatives
        if negatives:
            strain.negatives.clear()
            for negative_name in negatives:
                negative = self.db.query(Negative).filter(Negative.name == negative_name).first()
                if not negative:
                    negative = Negative(name=negative_name)
                    self.db.add(negative)
                    self.db.commit()
                    self.db.refresh(negative)
                strain.negatives.append(negative)
        
        # Update flavors
        if flavors:
            strain.flavors.clear()
            for flavor_name in flavors:
                flavor = self.db.query(Flavor).filter(Flavor.name == flavor_name).first()
                if not flavor:
                    flavor = Flavor(name=flavor_name)
                    self.db.add(flavor)
                    self.db.commit()
                    self.db.refresh(flavor)
                strain.flavors.append(flavor)
        
        self.db.commit()
        self.db.refresh(strain)
        return strain
    
    def search_strains_with_filters(
        self, 
        query: str, 
        filters: Dict[str, Any], 
        limit: int = 5
    ) -> List[StrainModel]:
        """Search strains with combined filters and query"""
        
        # Start with base query
        query_obj = self.db.query(StrainModel).options(
            joinedload(StrainModel.feelings),
            joinedload(StrainModel.helps_with),
            joinedload(StrainModel.negatives),
            joinedload(StrainModel.flavors)
        )
        
        # Apply filters if provided
        if filters:
            # Category filter
            if 'preferred_categories' in filters:
                categories = filters['preferred_categories']
                if categories:
                    query_obj = query_obj.filter(StrainModel.category.in_(categories))
            
            # Effects filter
            if 'effects' in filters:
                effects = filters['effects']
                
                # Required effects
                if effects.get('desired'):
                    for effect in effects['desired']:
                        query_obj = query_obj.join(StrainModel.feelings).filter(
                            Feeling.name == effect
                        )
                
                # Avoid effects  
                if effects.get('avoid'):
                    for effect in effects['avoid']:
                        # Subquery to exclude strains with these effects
                        exclude_subquery = self.db.query(StrainModel.id).join(
                            StrainModel.feelings
                        ).filter(Feeling.name == effect).subquery()
                        
                        query_obj = query_obj.filter(
                            ~StrainModel.id.in_(exclude_subquery)
                        )
            
            # Potency filter
            if 'potency' in filters and filters['potency'].get('thc'):
                thc_pref = filters['potency']['thc']
                if thc_pref == 'higher':
                    query_obj = query_obj.filter(StrainModel.thc >= 15.0)
                elif thc_pref == 'lower':
                    query_obj = query_obj.filter(StrainModel.thc < 15.0)
        
        # Execute query with limit
        strains = query_obj.limit(limit).all()
        
        return strains
    
    def search_strains_by_name(self, name: str) -> List[StrainModel]:
        """Search strains by name (partial match)"""
        
        return self.db.query(StrainModel).options(
            joinedload(StrainModel.feelings),
            joinedload(StrainModel.helps_with),
            joinedload(StrainModel.negatives),
            joinedload(StrainModel.flavors)
        ).filter(
            StrainModel.name.ilike(f"%{name}%")
        ).limit(5).all() 