import logging
from typing import List, Dict, Any, Optional
from app.models.schemas import Strain
from app.db.repository import StrainRepository

logger = logging.getLogger(__name__)


class AdaptiveStrainSearch:
    """Адаптивная система поиска с ослаблением фильтров"""
    
    def __init__(self, repository: StrainRepository):
        self.repository = repository
    
    def search_with_adaptive_filters(
        self, 
        query: str, 
        criteria: Optional[Dict[str, Any]], 
        limit: int = 5
    ) -> List[Strain]:
        """Адаптивный поиск: начинаем со строгих фильтров, ослабляем если нет результатов"""
        
        if not criteria:
            # Без критериев - простой поиск
            return self.repository.search_strains_with_filters(query, {}, limit)
        
        # Этап 1: Максимально строгие фильтры
        strains = self._search_strict(query, criteria, limit)
        if strains:
            logger.info(f"Adaptive search: found {len(strains)} strains with strict filters")
            return strains
        
        # Этап 2: Ослабляем фильтры эффектов
        strains = self._search_relaxed_effects(query, criteria, limit)  
        if strains:
            logger.info(f"Adaptive search: found {len(strains)} strains with relaxed effects")
            return strains
        
        # Этап 3: Только категории без эффектов
        strains = self._search_categories_only(query, criteria, limit)
        if strains:
            logger.info(f"Adaptive search: found {len(strains)} strains with categories only")
            return strains
        
        # Этап 4: Семантический поиск без фильтров
        strains = self._search_semantic_only(query, limit)
        if strains:
            logger.info(f"Adaptive search: found {len(strains)} strains with semantic search")
            return strains
        
        # Этап 5: Последний шанс - топ сорта
        strains = self._search_fallback(limit)
        logger.info(f"Adaptive search: fallback to top {len(strains)} strains")
        return strains
    
    def _search_strict(self, query: str, criteria: Dict[str, Any], limit: int) -> List[Strain]:
        """Этап 1: Строгие фильтры - все критерии"""
        
        filters = {}
        
        # Категории
        if 'effects' in criteria:
            effects = criteria['effects']
            
            # Определяем предпочтительные категории на основе эффектов
            desired = set(effects.get('desired', []))
            if desired & {'Sleepy', 'Relaxed', 'Couch Lock'}:
                filters['preferred_categories'] = ['Indica', 'Hybrid']
            elif desired & {'Energetic', 'Uplifted', 'Focused'}:
                filters['preferred_categories'] = ['Sativa', 'Hybrid']
            else:
                filters['preferred_categories'] = ['Indica', 'Sativa', 'Hybrid']
            
            # Эффекты
            filters['effects'] = effects
        
        # Потенциальность
        if 'potency' in criteria:
            filters['potency'] = criteria['potency']
        
        return self.repository.search_strains_with_filters(query, filters, limit)
    
    def _search_relaxed_effects(self, query: str, criteria: Dict[str, Any], limit: int) -> List[Strain]:
        """Этап 2: Ослабленные фильтры эффектов - только desired, убираем avoid"""
        
        filters = {}
        
        if 'effects' in criteria:
            effects = criteria['effects']
            desired = set(effects.get('desired', []))
            
            # Категории на основе эффектов
            if desired & {'Sleepy', 'Relaxed'}:
                filters['preferred_categories'] = ['Indica', 'Hybrid']
            elif desired & {'Energetic', 'Uplifted'}:
                filters['preferred_categories'] = ['Sativa', 'Hybrid'] 
            
            # Только required эффекты, убираем avoid
            filters['effects'] = {
                'desired': effects.get('desired', [])
                # НЕ включаем 'avoid' - ослабляем фильтр
            }
        
        return self.repository.search_strains_with_filters(query, filters, limit)
    
    def _search_categories_only(self, query: str, criteria: Dict[str, Any], limit: int) -> List[Strain]:
        """Этап 3: Только категории, без эффектов"""
        
        filters = {}
        
        if 'effects' in criteria:
            effects = criteria['effects']
            desired = set(effects.get('desired', []))
            
            # Только категории
            if desired & {'Sleepy', 'Relaxed', 'Couch Lock'}:
                filters['preferred_categories'] = ['Indica']
            elif desired & {'Energetic', 'Uplifted', 'Focused'}:
                filters['preferred_categories'] = ['Sativa']
            else:
                filters['preferred_categories'] = ['Hybrid']
        
        return self.repository.search_strains_with_filters(query, filters, limit)
    
    def _search_semantic_only(self, query: str, limit: int) -> List[Strain]:
        """Этап 4: Только семантический поиск без фильтров"""
        
        # Используем старый проверенный метод семантического поиска
        try:
            # Генерируем embedding для запроса
            from app.core.llm_interface import get_llm
            llm = get_llm()
            query_embedding = llm.generate_embedding(query)
            
            # Поиск похожих сортов по embedding
            strains = self.repository.search_similar_strains(query_embedding, limit)
            return strains
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    def _search_fallback(self, limit: int) -> List[Strain]:
        """Этап 5: Fallback - просто топ сорта"""
        
        # Получаем любые активные сорта
        return self.repository.search_strains_with_filters("", {}, limit)
    
    def explain_search_strategy(
        self, 
        query: str, 
        criteria: Optional[Dict[str, Any]], 
        found_strains: List[Strain]
    ) -> Dict[str, Any]:
        """Объяснение стратегии поиска для debugging"""
        
        explanation = {
            "query": query,
            "criteria": criteria,
            "found_count": len(found_strains),
            "search_stages": []
        }
        
        # Тестируем каждый этап чтобы понять где сработало
        if criteria:
            # Этап 1
            strict_results = self._search_strict(query, criteria, 10)
            explanation["search_stages"].append({
                "stage": 1,
                "description": "Strict filters (all criteria)",
                "found": len(strict_results)
            })
            
            if not strict_results:
                # Этап 2  
                relaxed_results = self._search_relaxed_effects(query, criteria, 10)
                explanation["search_stages"].append({
                    "stage": 2,
                    "description": "Relaxed effects (no avoid filters)",
                    "found": len(relaxed_results)
                })
                
                if not relaxed_results:
                    # Этап 3
                    category_results = self._search_categories_only(query, criteria, 10)
                    explanation["search_stages"].append({
                        "stage": 3,
                        "description": "Categories only",
                        "found": len(category_results)
                    })
        
        return explanation