"""
Category Filter - Простая система фильтрации по категории

Архитектура:
- CategoryFilter: фильтрация по Indica/Sativa/Hybrid
- ActiveOnlyFilter: только активные сорта
- FilterChain: комбинирование фильтров
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from sqlalchemy.orm import Query
from app.models.database import Strain as StrainModel
import logging

logger = logging.getLogger(__name__)


class StrainFilter(ABC):
    """Базовый интерфейс для фильтров сортов"""

    @abstractmethod
    def apply(self, query: Query) -> Query:
        """Применить фильтр к SQL запросу"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Название фильтра для логирования"""
        pass


class CategoryFilter(StrainFilter):
    """Фильтр по категории сорта (Indica/Sativa/Hybrid)"""

    def __init__(self, category: str):
        if category not in ["Indica", "Sativa", "Hybrid"]:
            raise ValueError(f"Invalid category: {category}. Must be Indica, Sativa, or Hybrid")
        self.category = category

    def apply(self, query: Query) -> Query:
        return query.filter(StrainModel.category == self.category)

    def get_name(self) -> str:
        return f"CategoryFilter({self.category})"


class ActiveOnlyFilter(StrainFilter):
    """Фильтр только активных сортов"""

    def apply(self, query: Query) -> Query:
        return query.filter(StrainModel.active == True)

    def get_name(self) -> str:
        return "ActiveOnlyFilter"


class THCRangeFilter(StrainFilter):
    """Фильтр по диапазону THC"""

    def __init__(self, min_thc: Optional[float] = None, max_thc: Optional[float] = None):
        self.min_thc = min_thc
        self.max_thc = max_thc

    def apply(self, query: Query) -> Query:
        if self.min_thc is not None:
            query = query.filter(StrainModel.thc >= self.min_thc)
        if self.max_thc is not None:
            query = query.filter(StrainModel.thc <= self.max_thc)
        return query

    def get_name(self) -> str:
        return f"THCRangeFilter(min={self.min_thc}, max={self.max_thc})"


class CBDRangeFilter(StrainFilter):
    """Фильтр по диапазону CBD"""

    def __init__(self, min_cbd: Optional[float] = None, max_cbd: Optional[float] = None):
        self.min_cbd = min_cbd
        self.max_cbd = max_cbd

    def apply(self, query: Query) -> Query:
        if self.min_cbd is not None:
            query = query.filter(StrainModel.cbd >= self.min_cbd)
        if self.max_cbd is not None:
            query = query.filter(StrainModel.cbd <= self.max_cbd)
        return query

    def get_name(self) -> str:
        return f"CBDRangeFilter(min={self.min_cbd}, max={self.max_cbd})"


class FilterChain:
    """
    Цепочка фильтров

    Example:
        >>> chain = FilterChain()
        >>> chain.add(CategoryFilter("Indica"))
        >>> results = chain.apply(base_query).all()
    """

    def __init__(self):
        self.filters: List[StrainFilter] = []

    def add(self, filter: StrainFilter) -> 'FilterChain':
        """Добавить фильтр в цепочку"""
        self.filters.append(filter)
        return self

    def apply(self, base_query: Query) -> Query:
        """Применить все фильтры последовательно"""
        query = base_query
        for filter in self.filters:
            logger.debug(f"Applying filter: {filter.get_name()}")
            query = filter.apply(query)

        logger.info(f"Applied {len(self.filters)} filters")
        return query

    def clear(self):
        """Очистить все фильтры"""
        self.filters = []

    def get_filter_names(self) -> List[str]:
        """Получить названия всех фильтров"""
        return [f.get_name() for f in self.filters]


class FilterFactory:
    """Factory для создания фильтров из параметров"""

    @staticmethod
    def create_from_params(params: dict) -> FilterChain:
        """
        Создать цепочку фильтров из параметров

        Args:
            params: {
                "category": "Indica|Sativa|Hybrid",
                "min_thc": float,
                "max_thc": float,
                "min_cbd": float,
                "max_cbd": float
            }

        Returns:
            FilterChain с созданными фильтрами
        """
        chain = FilterChain()

        # Всегда добавляем ActiveOnlyFilter
        chain.add(ActiveOnlyFilter())

        # Category filter
        category = params.get("category")
        if category and category in ["Indica", "Sativa", "Hybrid"]:
            chain.add(CategoryFilter(category))

        # THC filter
        min_thc = params.get("min_thc")
        max_thc = params.get("max_thc")
        if min_thc is not None or max_thc is not None:
            chain.add(THCRangeFilter(min_thc, max_thc))

        # CBD filter
        min_cbd = params.get("min_cbd")
        max_cbd = params.get("max_cbd")
        if min_cbd is not None or max_cbd is not None:
            chain.add(CBDRangeFilter(min_cbd, max_cbd))

        logger.info(f"Created filter chain: {chain.get_filter_names()}")
        return chain
