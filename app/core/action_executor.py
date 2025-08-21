from typing import List, Dict, Any, Optional
from app.models.schemas import Strain
from app.core.smart_query_analyzer import ActionPlan
from app.db.repository import StrainRepository
import logging

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    Action Executor для Smart Query Analyzer v3.0
    Выполняет действия на основе AI планов выполнения
    """
    
    def __init__(self, repository: StrainRepository):
        self.repository = repository
        self.executors = {
            "sort_strains": self._execute_sort_strains,
            "filter_strains": self._execute_filter_strains,
            "select_strains": self._execute_select_strains,
            "explain_strains": self._execute_explain_strains,
            "expand_search": self._execute_expand_search
        }
    
    def execute_action(
        self,
        action_plan: ActionPlan,
        session_strains: List[Strain]
    ) -> List[Strain]:
        """Главный метод выполнения действия по AI плану"""
        
        action_name = action_plan.primary_action
        parameters = action_plan.parameters
        
        logger.info(f"Executing action: {action_name} with parameters: {parameters}")
        
        # Получение соответствующего исполнителя
        executor = self.executors.get(action_name)
        if not executor:
            logger.error(f"Unknown action: {action_name}")
            return session_strains  # Возвращаем исходные сорта
        
        try:
            # Выполнение действия
            result_strains = executor(session_strains, parameters)
            
            logger.info(f"Action {action_name} completed: {len(result_strains)} strains returned")
            return result_strains
            
        except Exception as e:
            logger.error(f"Action {action_name} failed: {e}")
            return session_strains  # Fallback к исходным сортам
    
    def _execute_sort_strains(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Исполнитель сортировки сортов"""
        
        sort_by = parameters.get("sort_by", "thc")
        sort_order = parameters.get("sort_order", "desc")
        exclude_invalid = parameters.get("exclude_invalid", [])
        limit = parameters.get("limit", len(strains))
        
        logger.info(f"Sorting by {sort_by} {sort_order}, exclude: {exclude_invalid}, limit: {limit}")
        
        # Фильтрация invalid значений если требуется
        valid_strains = strains
        if exclude_invalid:
            valid_strains = self._filter_invalid_data(strains, sort_by, exclude_invalid)
            logger.info(f"Filtered invalid data: {len(strains)} -> {len(valid_strains)} strains")
        
        # Сортировка
        try:
            if sort_by == "thc":
                valid_strains.sort(
                    key=lambda s: float(s.thc) if s.thc and self._is_valid_number(s.thc) else 0,
                    reverse=(sort_order == "desc")
                )
            elif sort_by == "cbd":
                valid_strains.sort(
                    key=lambda s: float(s.cbd) if s.cbd and self._is_valid_number(s.cbd) else 0,
                    reverse=(sort_order == "desc")
                )
            elif sort_by == "name":
                valid_strains.sort(
                    key=lambda s: s.name.lower() if s.name else "",
                    reverse=(sort_order == "desc")
                )
            elif sort_by == "category":
                valid_strains.sort(
                    key=lambda s: s.category.lower() if s.category else "",
                    reverse=(sort_order == "desc")
                )
            
        except Exception as e:
            logger.error(f"Sorting failed: {e}")
            # Возвращаем несортированные, но отфильтрованные
        
        # Ограничение количества
        result = valid_strains[:limit] if limit > 0 else valid_strains
        
        logger.info(f"Sorting completed: {len(result)} strains")
        return result
    
    def _execute_filter_strains(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Исполнитель фильтрации сортов"""
        
        criteria = parameters.get("criteria", {})
        logger.info(f"Filtering with criteria: {criteria}")
        
        filtered_strains = strains.copy()
        
        # Фильтрация по категории
        if "category" in criteria:
            target_category = criteria["category"].lower()
            filtered_strains = [
                s for s in filtered_strains
                if s.category and s.category.lower() == target_category
            ]
            logger.info(f"Category filter: {len(filtered_strains)} strains match {target_category}")
        
        # Фильтрация по эффектам
        if "effects" in criteria:
            effects_criteria = criteria["effects"]
            
            # Желаемые эффекты
            if "desired" in effects_criteria:
                desired_effects = set(effects_criteria["desired"])
                filtered_strains = [
                    s for s in filtered_strains
                    if s.feelings and any(
                        f.name in desired_effects for f in s.feelings
                    )
                ]
                logger.info(f"Desired effects filter: {len(filtered_strains)} strains")
            
            # Нежелательные эффекты
            if "avoid" in effects_criteria:
                avoid_effects = set(effects_criteria["avoid"])
                filtered_strains = [
                    s for s in filtered_strains
                    if not s.feelings or not any(
                        f.name in avoid_effects for f in s.feelings
                    )
                ]
                logger.info(f"Avoid effects filter: {len(filtered_strains)} strains")
        
        # Фильтрация по потенции
        if "potency" in criteria:
            potency = criteria["potency"]
            if "min_thc" in potency:
                min_thc = float(potency["min_thc"])
                filtered_strains = [
                    s for s in filtered_strains
                    if s.thc and self._is_valid_number(s.thc) and float(s.thc) >= min_thc
                ]
            if "max_thc" in potency:
                max_thc = float(potency["max_thc"])
                filtered_strains = [
                    s for s in filtered_strains
                    if s.thc and self._is_valid_number(s.thc) and float(s.thc) <= max_thc
                ]
        
        logger.info(f"Filtering completed: {len(filtered_strains)} strains")
        return filtered_strains
    
    def _execute_select_strains(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Исполнитель выбора конкретных сортов"""
        
        selection_criteria = parameters.get("criteria", {})
        logger.info(f"Selecting strains with criteria: {selection_criteria}")
        
        # Выбор по индексу
        if "index" in selection_criteria:
            try:
                index = int(selection_criteria["index"])
                if 0 <= index < len(strains):
                    selected = [strains[index]]
                    logger.info(f"Selected strain by index {index}: {selected[0].name}")
                    return selected
                else:
                    logger.warning(f"Index {index} out of range for {len(strains)} strains")
            except ValueError:
                logger.error(f"Invalid index value: {selection_criteria['index']}")
        
        # Выбор по имени
        if "name" in selection_criteria:
            target_name = selection_criteria["name"].lower()
            selected = [
                s for s in strains
                if s.name and target_name in s.name.lower()
            ]
            logger.info(f"Selected {len(selected)} strains by name '{target_name}'")
            return selected
        
        # Выбор по ID
        if "id" in selection_criteria:
            target_id = selection_criteria["id"]
            selected = [s for s in strains if s.id == target_id]
            logger.info(f"Selected {len(selected)} strains by ID {target_id}")
            return selected
        
        # Если нет критериев - возвращаем все
        logger.info("No specific selection criteria, returning all strains")
        return strains
    
    def _execute_explain_strains(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Исполнитель объяснения характеристик сортов"""
        
        # Для explain просто возвращаем исходные сорта
        # Детальное объяснение будет в natural_response от AI
        logger.info(f"Explaining {len(strains)} strains")
        return strains
    
    def _execute_expand_search(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Исполнитель расширения поиска новыми сортами"""
        
        search_criteria = parameters.get("criteria", {})
        limit = parameters.get("limit", 5)
        
        logger.info(f"Expanding search with criteria: {search_criteria}, limit: {limit}")
        
        # Поиск новых сортов через repository
        try:
            new_strains = self._search_new_strains(search_criteria, limit)
            
            # Объединение с существующими сортами (избегая дубликатов)
            existing_ids = {s.id for s in strains}
            unique_new_strains = [s for s in new_strains if s.id not in existing_ids]
            
            combined_strains = strains + unique_new_strains
            logger.info(f"Search expansion: added {len(unique_new_strains)} new strains")
            
            return combined_strains[:limit] if limit > 0 else combined_strains
            
        except Exception as e:
            logger.error(f"Search expansion failed: {e}")
            return strains  # Fallback к исходным сортам
    
    def _filter_invalid_data(
        self,
        strains: List[Strain],
        field: str,
        invalid_values: List[str]
    ) -> List[Strain]:
        """Фильтрация сортов с невалидными данными"""
        
        valid_strains = []
        invalid_indicators = [v.lower() for v in invalid_values] + ['', '0', '0.0', '0.00']
        
        for strain in strains:
            field_value = getattr(strain, field, None)
            
            if field_value is None:
                continue
            
            str_value = str(field_value).strip().lower()
            
            if str_value in invalid_indicators:
                continue
            
            # Для числовых полей проверяем валидность числа
            if field in ["thc", "cbd", "cbg"]:
                if not self._is_valid_number(field_value):
                    continue
            
            valid_strains.append(strain)
        
        return valid_strains
    
    def _is_valid_number(self, value: Any) -> bool:
        """Проверка валидности числового значения"""
        
        if value is None:
            return False
        
        try:
            num_value = float(str(value))
            return num_value >= 0  # Неотрицательное число
        except (ValueError, TypeError):
            return False
    
    def _search_new_strains(
        self,
        criteria: Dict[str, Any],
        limit: int
    ) -> List[Strain]:
        """Поиск новых сортов в базе данных"""
        
        # Базовый поиск - можно расширить более сложными критериями
        try:
            if "category" in criteria:
                strains = self.repository.get_strains_by_category(
                    criteria["category"],
                    limit=limit
                )
            elif "min_thc" in criteria:
                strains = self.repository.get_strains_by_thc_range(
                    min_thc=criteria["min_thc"],
                    max_thc=criteria.get("max_thc", 100),
                    limit=limit
                )
            else:
                # Общий поиск
                strains = self.repository.get_strains(limit=limit)
            
            return strains
            
        except Exception as e:
            logger.error(f"Database search failed: {e}")
            return []
    
    def get_execution_summary(self, action_plan: ActionPlan, result_count: int) -> Dict[str, Any]:
        """Получение сводки выполнения действия"""
        
        return {
            "action_executed": action_plan.primary_action,
            "parameters_used": action_plan.parameters,
            "reasoning": action_plan.reasoning,
            "result_count": result_count,
            "execution_successful": result_count >= 0
        }