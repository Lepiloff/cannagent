from typing import List, Dict, Any, Optional, Union
from app.models.schemas import Strain
from app.core.smart_query_analyzer import ActionPlan
from app.db.repository import StrainRepository
import logging

logger = logging.getLogger(__name__)


class UniversalActionExecutor:
    """
    Universal Action Executor для Smart Query Executor v3.0
    Выполняет действия на основе гибких AI-генерируемых критериев
    БЕЗ хардкода для каждого типа поля
    """
    
    def __init__(self, repository: StrainRepository):
        self.repository = repository
        self.executors = {
            "sort_strains": self._execute_sort_strains,
            "filter_strains": self._execute_filter_strains, 
            "select_strains": self._execute_select_strains,
            "explain_strains": self._execute_explain_strains,
            "search_strains": self._execute_search_strains,  # Новый универсальный поиск
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
        
        logger.info(f"Executing universal action: {action_name}")
        logger.debug(f"Parameters: {parameters}")
        
        # Получение соответствующего исполнителя
        executor = self.executors.get(action_name)
        if not executor:
            logger.error(f"Unknown action: {action_name}")
            return session_strains  # Fallback
        
        try:
            # Выполнение действия
            result_strains = executor(session_strains, parameters)
            
            logger.info(f"Action {action_name} completed: {len(result_strains)} strains returned")
            return result_strains
            
        except Exception as e:
            logger.error(f"Action {action_name} failed: {e}")
            logger.debug(f"Session strains fallback: {len(session_strains)} strains")
            return session_strains  # Fallback
    
    def _execute_search_strains(
        self,
        session_strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Универсальный поиск сортов по AI критериям с медицинской приоритизацией"""
        
        filters = parameters.get("filters", {})
        scoring = parameters.get("scoring", {})
        sort_config = parameters.get("sort", {})
        limit = parameters.get("limit", 5)
        
        logger.info(f"Medical-aware search: filters={len(filters)} criteria, scoring={scoring}")
        
        # Получаем все сорта из базы
        try:
            all_strains = self.repository.get_strains_with_relations(limit=200)
            logger.info(f"Loaded {len(all_strains)} strains from database")
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return []
        
        # Проверяем метод scoring
        scoring_method = scoring.get("method", "simple_sort")
        
        if scoring_method == "weighted_priority":
            # Используем медицински-осознанную систему scoring
            scored_strains = self._apply_weighted_priority_scoring(all_strains, filters)
            logger.info(f"Applied weighted priority scoring: {len(scored_strains)} strains scored")
        else:
            # Применяем обычные фильтры
            scored_strains = [(strain, 1.0) for strain in self._apply_universal_filters(all_strains, filters)]
        
        # Медицинские queries: сначала по медицинскому score, затем по числовым критериям
        if scoring.get("method") == "weighted_priority":
            # Sort by medical score first, then apply secondary numerical sorting
            sorted_strains = sorted(scored_strains, key=lambda x: x[1], reverse=True)
            sorted_strains = self._apply_secondary_numerical_sorting(sorted_strains, filters)
            logger.info(f"Medical + numerical sorted results: {[(s[0].name, round(s[1], 3)) for s in sorted_strains[:3]]}")
        elif sort_config.get("field") == "score":
            sorted_strains = sorted(scored_strains, key=lambda x: x[1], reverse=(sort_config.get("order", "desc") == "desc"))
        else:
            strain_list = [s[0] for s in scored_strains]
            sorted_strain_list = self._apply_universal_sort(strain_list, sort_config)
            sorted_strains = [(s, 1.0) for s in sorted_strain_list]
        
        # Извлекаем только strain объекты и ограничиваем результат
        result_strains = [s[0] for s in sorted_strains[:limit]]
        
        logger.info(f"Medical-aware search result: {len(result_strains)} strains")
        return result_strains
    
    def _execute_sort_strains(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Универсальная сортировка существующих сортов"""
        
        # Support both old format (sort_by, sort_order) and new format (sort object)
        if "sort" in parameters and isinstance(parameters["sort"], dict):
            sort_config = {
                "field": parameters["sort"].get("field", "thc"),
                "order": parameters["sort"].get("order", "desc")
            }
        else:
            sort_config = {
                "field": parameters.get("sort_by", "thc"),
                "order": parameters.get("sort_order", "desc")
            }
        exclude_invalid = parameters.get("exclude_invalid", [])
        limit = parameters.get("limit", len(strains))
        
        logger.info(f"Universal sort: {sort_config}, exclude_invalid={exclude_invalid}")
        
        # Фильтрация invalid значений если требуется
        valid_strains = strains
        if exclude_invalid:
            valid_strains = self._filter_out_invalid_data(
                strains, 
                sort_config["field"], 
                exclude_invalid
            )
            logger.info(f"Filtered invalid: {len(strains)} -> {len(valid_strains)} strains")
        
        # Применяем универсальную сортировку
        sorted_strains = self._apply_universal_sort(valid_strains, sort_config)
        
        # Ограничиваем результат
        result = sorted_strains[:limit] if limit > 0 else sorted_strains
        return result
    
    def _execute_filter_strains(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Универсальная фильтрация существующих сортов"""
        
        filters = parameters.get("filters", parameters.get("criteria", {}))  # Поддержка обоих форматов
        logger.info(f"Universal filter with: {filters}")
        
        # Применяем универсальные фильтры
        filtered_strains = self._apply_universal_filters(strains, filters)
        logger.info(f"Filtering result: {len(strains)} -> {len(filtered_strains)} strains")
        
        return filtered_strains
    
    def _execute_select_strains(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Выбор конкретных сортов по AI критериям"""
        
        selection = parameters.get("selection", parameters.get("criteria", {}))
        logger.info(f"Universal selection: {selection}")
        
        # Выбор по индексу
        if "index" in selection:
            try:
                index = int(selection["index"])
                if 0 <= index < len(strains):
                    return [strains[index]]
            except (ValueError, IndexError):
                logger.warning(f"Invalid index: {selection['index']}")
        
        # Выбор по имени (частичное совпадение)
        if "name" in selection:
            target_name = selection["name"].lower()
            matches = [s for s in strains if s.name and target_name in s.name.lower()]
            if matches:
                logger.info(f"Found {len(matches)} strains matching name '{target_name}'")
                return matches
        
        # Выбор по ID
        if "id" in selection:
            target_id = selection["id"]
            matches = [s for s in strains if s.id == target_id]
            return matches
        
        # Если нет критериев - возвращаем все
        logger.info("No specific selection criteria, returning all strains")
        return strains
    
    def _execute_explain_strains(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Объяснение характеристик - просто возвращаем сорта"""
        logger.info(f"Explaining {len(strains)} strains")
        return strains
    
    def _execute_expand_search(
        self,
        strains: List[Strain],
        parameters: Dict[str, Any]
    ) -> List[Strain]:
        """Расширение поиска - используем универсальный поиск"""
        
        # Перенаправляем на универсальный поиск
        new_strains = self._execute_search_strains([], parameters)
        
        # Объединяем с существующими, избегая дубликатов
        existing_ids = {s.id for s in strains}
        unique_new_strains = [s for s in new_strains if s.id not in existing_ids]
        
        combined = strains + unique_new_strains
        limit = parameters.get("limit", 10)
        
        logger.info(f"Expand search: added {len(unique_new_strains)} new strains")
        return combined[:limit]
    
    def _apply_universal_filters(
        self, 
        strains: List[Strain], 
        filters: Dict[str, Any]
    ) -> List[Strain]:
        """
        Универсальная система фильтрации
        Поддерживает любые поля и операторы через AI критерии
        """
        
        if not filters:
            return strains
        
        filtered_strains = []
        
        for strain in strains:
            if self._strain_matches_filters(strain, filters):
                filtered_strains.append(strain)
        
        return filtered_strains
    
    def _strain_matches_filters(self, strain: Strain, filters: Dict[str, Any]) -> bool:
        """Проверка соответствия сорта универсальным фильтрам"""
        
        for field_name, filter_config in filters.items():
            if not self._field_matches_filter(strain, field_name, filter_config):
                return False
        
        return True
    
    def _field_matches_filter(
        self, 
        strain: Strain, 
        field_name: str, 
        filter_config: Union[Dict[str, Any], Any]
    ) -> bool:
        """Универсальная проверка поля по фильтру"""
        
        # Получаем значение поля из сорта
        field_value = self._get_strain_field_value(strain, field_name)
        
        # Если фильтр - простое значение (например "Indica")
        if not isinstance(filter_config, dict):
            return self._simple_match(field_value, filter_config)
        
        # Если фильтр - сложный с оператором
        operator = filter_config.get("operator", "eq")
        target_value = filter_config.get("value")
        target_values = filter_config.get("values", [])
        
        if operator == "eq":
            return self._simple_match(field_value, target_value)
        elif operator == "gte" or operator == ">=":
            return self._numeric_compare(field_value, target_value, ">=")
        elif operator == "lte" or operator == "<=":
            return self._numeric_compare(field_value, target_value, "<=")
        elif operator == "gt" or operator == ">":
            return self._numeric_compare(field_value, target_value, ">")
        elif operator == "lt" or operator == "<":
            return self._numeric_compare(field_value, target_value, "<")
        elif operator == "contains":
            return self._contains_match(field_value, target_values or [target_value])
        elif operator == "any":
            return self._any_match(field_value, target_values)
        elif operator == "not_contains":
            return not self._contains_match(field_value, target_values or [target_value])
        
        logger.warning(f"Unknown operator: {operator}")
        return True  # Не исключаем при неизвестном операторе
    
    def _get_strain_field_value(self, strain: Strain, field_name: str) -> Any:
        """Универсальное получение значения поля сорта"""
        
        # Прямые поля
        if hasattr(strain, field_name):
            return getattr(strain, field_name)
        
        # Специальные случаи для связанных объектов
        if field_name == "effects" or field_name == "feelings":
            return [f.name for f in strain.feelings] if strain.feelings else []
        elif field_name == "helps_with" or field_name == "medical":
            return [h.name for h in strain.helps_with] if strain.helps_with else []
        elif field_name == "negatives" or field_name == "side_effects":
            return [n.name for n in strain.negatives] if strain.negatives else []
        elif field_name == "flavors":
            return [fl.name for fl in strain.flavors] if strain.flavors else []
        
        # Числовые поля с очисткой
        elif field_name in ["thc", "cbd", "cbg"]:
            raw_value = getattr(strain, field_name, None)
            return self._clean_numeric_value(raw_value)
        
        return None
    
    def _simple_match(self, field_value: Any, target: Any) -> bool:
        """Простое сравнение значений"""
        
        if field_value is None or target is None:
            return field_value == target
        
        # Строковое сравнение (без учета регистра)
        if isinstance(field_value, str) and isinstance(target, str):
            return field_value.lower() == target.lower()
        
        return field_value == target
    
    def _numeric_compare(self, field_value: Any, target: Any, operator: str) -> bool:
        """Числовое сравнение"""
        
        try:
            field_num = self._to_number(field_value)
            target_num = self._to_number(target)
            
            if field_num is None or target_num is None:
                return False
            
            if operator == ">=":
                return field_num >= target_num
            elif operator == "<=":
                return field_num <= target_num
            elif operator == ">":
                return field_num > target_num
            elif operator == "<":
                return field_num < target_num
            
        except (ValueError, TypeError):
            return False
        
        return False
    
    def _contains_match(self, field_value: Any, targets: List[Any]) -> bool:
        """Проверка содержания (для массивов эффектов, ароматов и т.д.)"""
        
        if not targets:
            return True
        
        # Если field_value - список
        if isinstance(field_value, list):
            field_set = {str(v).lower() for v in field_value}
            target_set = {str(t).lower() for t in targets}
            return bool(field_set & target_set)  # Пересечение множеств
        
        # Если field_value - строка
        if isinstance(field_value, str):
            field_lower = field_value.lower()
            return any(str(t).lower() in field_lower for t in targets)
        
        return False
    
    def _any_match(self, field_value: Any, targets: List[Any]) -> bool:
        """Проверка любого совпадения"""
        
        if not targets:
            return True
        
        # Если field_value - список
        if isinstance(field_value, list):
            field_set = {str(v).lower() for v in field_value}
            target_set = {str(t).lower() for t in targets}
            return bool(field_set & target_set)
        
        # Если field_value - строка или другой тип
        field_str = str(field_value).lower() if field_value else ""
        return any(str(t).lower() == field_str for t in targets)
    
    def _apply_universal_sort(
        self, 
        strains: List[Strain], 
        sort_config: Dict[str, Any]
    ) -> List[Strain]:
        """Универсальная сортировка по любому полю"""
        
        if not sort_config or not strains:
            return strains
        
        field = sort_config.get("field", "name")
        order = sort_config.get("order", "asc")
        reverse = (order.lower() == "desc")
        
        logger.info(f"Sorting by {field} ({order})")
        
        try:
            sorted_strains = sorted(
                strains,
                key=lambda s: self._get_sort_key(s, field),
                reverse=reverse
            )
            return sorted_strains
            
        except Exception as e:
            logger.error(f"Sorting failed: {e}")
            return strains  # Возвращаем несортированные
    
    def _get_sort_key(self, strain: Strain, field: str) -> Any:
        """Универсальное получение ключа сортировки"""
        
        value = self._get_strain_field_value(strain, field)
        
        # Для числовых полей
        if field in ["thc", "cbd", "cbg"]:
            numeric = self._to_number(value)
            return numeric if numeric is not None else -1  # Invalid values в конец
        
        # Для строковых полей
        if isinstance(value, str):
            return value.lower()
        
        # Для списков (длина)
        if isinstance(value, list):
            return len(value)
        
        # Для остального
        return str(value) if value is not None else ""
    
    def _filter_out_invalid_data(
        self,
        strains: List[Strain],
        field: str,
        invalid_indicators: List[str]
    ) -> List[Strain]:
        """Универсальная фильтрация невалидных данных"""
        
        valid_strains = []
        invalid_set = {v.lower() for v in invalid_indicators}
        
        for strain in strains:
            field_value = self._get_strain_field_value(strain, field)
            
            if field_value is None:
                continue
            
            # Проверка на невалидные значения
            str_value = str(field_value).strip().lower()
            if str_value in invalid_set or str_value in ["", "0", "0.0", "0.00"]:
                continue
            
            # Для числовых полей - дополнительная проверка
            if field in ["thc", "cbd", "cbg"]:
                if self._to_number(field_value) is None:
                    continue
            
            valid_strains.append(strain)
        
        return valid_strains
    
    def _apply_weighted_priority_scoring(
        self, 
        strains: List[Strain], 
        filters: Dict[str, Any]
    ) -> List[tuple]:
        """Медицински-осознанная система scoring с приоритетами"""
        
        scored_strains = []
        
        for strain in strains:
            total_score = self._calculate_strain_priority_score(strain, filters)
            scored_strains.append((strain, total_score))
        
        logger.info(f"Applied weighted priority scoring: {len(scored_strains)} strains scored")
        return scored_strains
    
    def _apply_medical_qualification_stage(
        self, 
        strains: List[Strain], 
        filters: Dict[str, Any]
    ) -> List[Strain]:
        """Stage 1: Medical Safety Qualification Filter (Priority 1 criteria)"""
        
        # Extract Priority 1 (medical) filters
        medical_filters = {
            field_name: config for field_name, config in filters.items() 
            if isinstance(config, dict) and config.get("priority") == 1
        }
        
        if not medical_filters:
            # No medical constraints - all strains qualify
            return strains
        
        qualified_strains = []
        
        for strain in strains:
            medical_qualification_score = 0.0
            total_medical_criteria = len(medical_filters)
            
            for field_name, filter_config in medical_filters.items():
                field_score = self._calculate_field_priority_score(strain, field_name, filter_config)
                medical_qualification_score += field_score
            
            # Medical Qualification Threshold: >= 50% of medical criteria must pass
            qualification_threshold = total_medical_criteria * 0.5
            
            if medical_qualification_score >= qualification_threshold:
                qualified_strains.append(strain)
            else:
                logger.debug(f"Medical disqualification: {strain.name} scored {medical_qualification_score}/{total_medical_criteria}")
        
        return qualified_strains
    
    def _apply_numerical_ranking_stage(
        self, 
        qualified_strains: List[Strain], 
        filters: Dict[str, Any]
    ) -> List[tuple]:
        """Stage 2: Multi-Criteria Numerical Ranking Engine (Priority 2+ criteria)"""
        
        if not qualified_strains:
            return []
        
        # Extract Priority 2+ (numerical/preference) filters
        ranking_filters = {
            field_name: config for field_name, config in filters.items() 
            if isinstance(config, dict) and config.get("priority", 2) > 1
        }
        
        ranked_strains = []
        
        for strain in qualified_strains:
            # Base qualification score (all qualified strains start equal)
            base_score = 1.0
            
            # Apply numerical ranking criteria
            ranking_score = self._calculate_numerical_ranking_score(strain, ranking_filters)
            
            # Data quality bonus
            data_quality_bonus = self._calculate_data_quality_bonus(strain)
            
            final_score = base_score + ranking_score + data_quality_bonus
            ranked_strains.append((strain, final_score))
        
        # Sort by final score (highest first - best matches on top)
        ranked_strains.sort(key=lambda x: x[1], reverse=True)
        
        return ranked_strains
    
    def _calculate_numerical_ranking_score(
        self, 
        strain: Strain, 
        ranking_filters: Dict[str, Any]
    ) -> float:
        """Calculate numerical ranking score with intelligent scaling"""
        
        if not ranking_filters:
            return 0.0
        
        total_ranking_score = 0.0
        
        for field_name, filter_config in ranking_filters.items():
            priority = filter_config.get("priority", 2)
            weight = self._get_priority_weight(priority) / 10.0  # Scale down for ranking stage
            
            field_score = self._calculate_field_priority_score(strain, field_name, filter_config)
            
            # For numerical fields with comparison operators, apply intelligent scaling
            if self._is_numerical_optimization_field(field_name, filter_config):
                field_score = self._apply_numerical_optimization_scaling(strain, field_name, filter_config)
            
            total_ranking_score += field_score * weight
        
        return total_ranking_score
    
    def _is_numerical_optimization_field(self, field_name: str, filter_config: Dict[str, Any]) -> bool:
        """Check if this is a numerical optimization field (THC, CBD, etc.)"""
        numerical_fields = {"thc", "cbd", "cbg"}
        optimization_operators = {"gte", "lte", "gt", "lt"}
        
        return (field_name.lower() in numerical_fields and 
                filter_config.get("operator") in optimization_operators)
    
    def _apply_numerical_optimization_scaling(
        self, 
        strain: Strain, 
        field_name: str, 
        filter_config: Dict[str, Any]
    ) -> float:
        """Apply intelligent scaling for numerical optimization (higher THC gets higher score)"""
        
        field_value = self._get_strain_field_value(strain, field_name)
        numeric_value = self._to_number(field_value)
        
        if numeric_value is None:
            return 0.0
        
        operator = filter_config.get("operator")
        target_value = self._to_number(filter_config.get("value"))
        
        if target_value is None:
            return 0.0
        
        # Intelligent scaling based on optimization direction
        if operator in ["gte", "gt"]:
            # Higher is better (e.g., "high THC")
            if numeric_value >= target_value:
                # Scale: meeting threshold gets 1.0, higher values get bonus up to 2.0
                excess_ratio = (numeric_value - target_value) / max(target_value, 1.0)
                return 1.0 + min(excess_ratio, 1.0)  # Cap bonus at 1.0
            else:
                # Below threshold gets proportional score
                return numeric_value / target_value
        
        elif operator in ["lte", "lt"]:
            # Lower is better (e.g., "low CBD")
            if numeric_value <= target_value:
                # Scale: meeting threshold gets 1.0, lower values get bonus up to 2.0
                if target_value > 0:
                    efficiency_ratio = (target_value - numeric_value) / target_value
                    return 1.0 + min(efficiency_ratio, 1.0)
                return 1.0
            else:
                # Above threshold gets proportional penalty
                return target_value / max(numeric_value, 0.1)
        
        return 1.0 if numeric_value >= target_value else 0.0
    
    def _calculate_strain_priority_score(self, strain: Strain, filters: Dict[str, Any]) -> float:
        """Penalty-Based Medical Scoring: Qualification + Penalties (not elimination)"""
        
        # Step 1: Medical Qualification Check (Priority 1)
        medical_qualification_score = self._calculate_medical_qualification(strain, filters)
        
        # Step 2: If medically qualified, calculate full score with penalties
        if medical_qualification_score > 0:
            return self._calculate_qualified_strain_score(strain, filters, medical_qualification_score)
        else:
            # Not medically qualified - low score but not eliminated
            return 0.1  # Minimal score for fallback options
    
    def _calculate_medical_qualification(self, strain: Strain, filters: Dict[str, Any]) -> float:
        """Check if strain meets primary medical criteria"""
        
        medical_criteria = {
            field_name: config for field_name, config in filters.items() 
            if isinstance(config, dict) and config.get("priority") == 1
        }
        
        if not medical_criteria:
            return 1.0  # No medical constraints
        
        primary_medical_score = 0.0
        medical_criteria_count = 0
        
        for field_name, filter_config in medical_criteria.items():
            # Check primary medical indications (helps_with)
            if field_name in ["helps_with", "medical"]:
                field_score = self._calculate_field_priority_score(strain, field_name, filter_config)
                if field_score > 0:
                    primary_medical_score += 1.0  # Basic qualification
                medical_criteria_count += 1
        
        # Require at least one primary medical indication
        return primary_medical_score / max(medical_criteria_count, 1)
    
    def _calculate_qualified_strain_score(
        self, 
        strain: Strain, 
        filters: Dict[str, Any],
        base_qualification: float
    ) -> float:
        """Calculate full score for medically qualified strain"""
        
        # Base score for medical qualification
        total_score = base_qualification * 2.0  # Strong base (2.0)
        
        # Add numerical bonuses (Priority 2)
        numerical_bonus = self._calculate_numerical_bonuses(strain, filters)
        total_score += numerical_bonus
        
        # Apply contradiction penalties (Priority 1 exclusions)
        contradiction_penalty = self._calculate_contradiction_penalties(strain, filters)
        total_score -= contradiction_penalty
        
        # Data quality bonus
        data_quality_bonus = self._calculate_data_quality_bonus(strain)
        total_score += data_quality_bonus
        
        # Ensure positive score for qualified strains
        return max(total_score, 0.2)
    
    def _calculate_numerical_bonuses(self, strain: Strain, filters: Dict[str, Any]) -> float:
        """Calculate bonuses for numerical criteria (THC, CBD, etc.)"""
        
        total_bonus = 0.0
        
        for field_name, filter_config in filters.items():
            if (isinstance(filter_config, dict) and 
                filter_config.get("priority", 2) == 2 and
                field_name.lower() in ["thc", "cbd", "cbg"]):
                
                field_value = self._get_strain_field_value(strain, field_name)
                numeric_value = self._to_number(field_value)
                
                if numeric_value is not None:
                    operator = filter_config.get("operator")
                    target_value = self._to_number(filter_config.get("value"))
                    
                    if target_value and operator in ["gte", "gt"]:
                        # Higher values get more bonus
                        if numeric_value >= target_value:
                            excess_ratio = (numeric_value - target_value) / max(target_value, 1.0)
                            bonus = 0.5 + min(excess_ratio * 0.5, 1.0)  # 0.5-1.5 bonus range
                            total_bonus += bonus
                            logger.debug(f"Numerical bonus: {strain.name} {field_name}={numeric_value} gets +{bonus:.2f}")
        
        return total_bonus
    
    def _calculate_contradiction_penalties(self, strain: Strain, filters: Dict[str, Any]) -> float:
        """Calculate penalties for contradictory effects (not elimination!)"""
        
        total_penalty = 0.0
        
        for field_name, filter_config in filters.items():
            if (isinstance(filter_config, dict) and 
                filter_config.get("priority") == 1 and 
                filter_config.get("operator") == "not_contains"):
                
                field_value = self._get_strain_field_value(strain, field_name)
                excluded_values = filter_config.get("values", [])
                
                if isinstance(field_value, list) and excluded_values:
                    # Count contradictions but apply graduated penalties
                    contradictions = [v for v in field_value if str(v).lower() in [str(e).lower() for e in excluded_values]]
                    
                    if contradictions:
                        # Graduated penalty: minor contradictions get smaller penalties
                        for contradiction in contradictions:
                            if str(contradiction).lower() in ["happy", "euphoric"]:
                                penalty = 0.2  # Minor penalty for mood effects
                            elif str(contradiction).lower() in ["uplifted", "creative"]:
                                penalty = 0.4  # Moderate penalty
                            elif str(contradiction).lower() in ["energetic", "talkative"]:
                                penalty = 0.6  # Higher penalty for truly contradictory effects
                            else:
                                penalty = 0.3  # Default moderate penalty
                            
                            total_penalty += penalty
                            logger.debug(f"Contradiction penalty: {strain.name} has {contradiction} = -{penalty:.1f}")
        
        return min(total_penalty, 1.5)  # Cap total penalty
    
    def _get_priority_weight(self, priority: int) -> float:
        """Получение веса по приоритету"""
        priority_weights = {
            1: 10.0,  # Медицинские показания - высший приоритет
            2: 3.0,   # Вторичные критерии (THC, CBD, category)
            3: 1.0    # Третичные критерии (flavors, appearance)
        }
        return priority_weights.get(priority, 1.0)
    
    def _calculate_field_priority_score(
        self, 
        strain: Strain, 
        field_name: str, 
        filter_config: Dict[str, Any]
    ) -> float:
        """Расчет score для конкретного поля с учетом приоритетов"""
        
        field_value = self._get_strain_field_value(strain, field_name)
        operator = filter_config.get("operator", "eq")
        target_value = filter_config.get("value")
        target_values = filter_config.get("values", [])
        
        # Для exclusion фильтров (not_contains)
        if operator == "not_contains":
            if self._contains_match(field_value, target_values or [target_value]):
                return 0.0  # Полное исключение
            else:
                return 1.0  # Полный балл за соответствие
        
        # Для inclusion фильтров
        if operator == "contains":
            if isinstance(field_value, list):
                matches = len([v for v in field_value if str(v).lower() in [str(t).lower() for t in target_values]])
                return min(matches / len(target_values), 1.0)  # Пропорциональный score
            return 1.0 if self._contains_match(field_value, target_values) else 0.0
        
        # Для числовых фильтров
        if operator in ["gte", ">=", "lte", "<=", "gt", ">", "lt", "<"]:
            if self._numeric_compare(field_value, target_value, operator):
                # Дополнительный score за превышение минимальных требований
                if operator in ["gte", ">="]:
                    field_num = self._to_number(field_value)
                    target_num = self._to_number(target_value)
                    if field_num and target_num and field_num > target_num:
                        # Бонус за превышение минимума (до 20% дополнительно)
                        bonus = min((field_num - target_num) / target_num * 0.2, 0.2)
                        return 1.0 + bonus
                return 1.0
            else:
                return 0.0
        
        # Для точного соответствия
        if operator == "eq":
            return 1.0 if self._simple_match(field_value, target_value) else 0.0
        
        # Для any совпадений
        if operator == "any":
            return 1.0 if self._any_match(field_value, target_values) else 0.0
        
        return 0.0
    
    def _calculate_data_quality_bonus(self, strain: Strain) -> float:
        """Бонус за качество данных сорта"""
        
        bonus = 0.0
        
        # Бонус за валидные числовые поля
        if self._to_number(strain.thc) is not None:
            bonus += 0.02
        if self._to_number(strain.cbd) is not None:
            bonus += 0.02
        if self._to_number(strain.cbg) is not None:
            bonus += 0.01
            
        # Бонус за наличие подробной информации
        if strain.feelings and len(strain.feelings) >= 2:
            bonus += 0.03
        if strain.helps_with and len(strain.helps_with) >= 2:
            bonus += 0.03
        if strain.flavors and len(strain.flavors) >= 2:
            bonus += 0.02
            
        # Штраф за отсутствие ключевой информации
        if not strain.feelings:
            bonus -= 0.05
        if not strain.helps_with:
            bonus -= 0.05
            
        return max(bonus, -0.1)  # Ограничиваем штраф
    
    def _apply_secondary_numerical_sorting(
        self, 
        primary_sorted_strains: List[tuple], 
        filters: Dict[str, Any]
    ) -> List[tuple]:
        """Вторичная сортировка по числовым критериям внутри одинаковых медицинских score"""
        
        if not primary_sorted_strains:
            return []
        
        # Найти числовые критерии Priority 2 с операторами сравнения
        numerical_criteria = []
        for field_name, filter_config in filters.items():
            if (isinstance(filter_config, dict) and 
                filter_config.get("priority", 2) == 2 and
                field_name.lower() in ["thc", "cbd", "cbg"] and
                filter_config.get("operator") in ["gte", "lte", "gt", "lt"]):
                
                numerical_criteria.append((field_name, filter_config))
        
        if not numerical_criteria:
            return primary_sorted_strains
        
        # Группируем по медицинскому score и сортируем внутри групп
        score_groups = {}
        for strain, med_score in primary_sorted_strains:
            med_score_rounded = round(med_score, 2)  # Группируем по округленному score
            if med_score_rounded not in score_groups:
                score_groups[med_score_rounded] = []
            score_groups[med_score_rounded].append((strain, med_score))
        
        # Сортируем каждую группу по числовым критериям
        final_sorted = []
        for med_score in sorted(score_groups.keys(), reverse=True):  # Лучший мед score первый
            group_strains = score_groups[med_score]
            
            # Вторичная сортировка по первому числовому критерию
            if numerical_criteria:
                field_name, filter_config = numerical_criteria[0]
                operator = filter_config.get("operator")
                
                reverse_sort = operator in ["gte", "gt"]  # Для "high THC" сортируем по убыванию
                
                group_strains.sort(
                    key=lambda x: self._get_numerical_sort_key(x[0], field_name), 
                    reverse=reverse_sort
                )
            
            final_sorted.extend(group_strains)
        
        return final_sorted
    
    def _get_numerical_sort_key(self, strain: Strain, field_name: str) -> float:
        """Получить числовой ключ для сортировки"""
        field_value = self._get_strain_field_value(strain, field_name)
        numeric_value = self._to_number(field_value)
        return numeric_value if numeric_value is not None else -1  # Невалидные значения в конец
    
    def _clean_numeric_value(self, value: Any) -> Optional[float]:
        """Очистка числового значения"""
        return self._to_number(value)
    
    def _to_number(self, value: Any) -> Optional[float]:
        """Универсальное преобразование в число"""
        
        if value is None:
            return None
        
        try:
            # Если уже число
            if isinstance(value, (int, float)):
                return float(value) if value >= 0 else None
            
            # Если строка
            str_value = str(value).strip()
            if str_value.lower() in ["", "n/a", "none", "null", "unknown"]:
                return None
            
            num_value = float(str_value)
            return num_value if num_value >= 0 else None
            
        except (ValueError, TypeError):
            return None
    
    def get_execution_summary(
        self, 
        action_plan: ActionPlan, 
        result_count: int
    ) -> Dict[str, Any]:
        """Сводка выполнения универсального действия"""
        
        return {
            "action_executed": action_plan.primary_action,
            "parameters_used": action_plan.parameters,
            "reasoning": action_plan.reasoning,
            "result_count": result_count,
            "execution_successful": result_count >= 0,
            "executor_type": "universal"
        }