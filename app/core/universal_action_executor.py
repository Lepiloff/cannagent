from typing import List, Dict, Any, Optional, Union
import math
from app.core.llm_interface import get_llm
from app.core.taxonomy import normalize_list, get_synonyms
from app.core.cache import cache_service
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
        self._llm = get_llm()
        self._flavor_embedding_cache: Dict[str, List[float]] = {}
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

        # Жёсткие фильтры (hard constraints) перед скорингом: категория
        source_strains = all_strains
        category_filter = None
        if isinstance(filters, dict) and "category" in filters:
            cf = filters.get("category")
            if isinstance(cf, dict) and cf.get("operator") == "eq" and cf.get("value"):
                category_filter = {"category": cf}
        if category_filter:
            prefiltered = self._apply_universal_filters(all_strains, category_filter)
            if prefiltered:
                source_strains = prefiltered
                logger.info(f"Applied hard category filter: {len(all_strains)} -> {len(source_strains)}")
            else:
                logger.info("Hard category filter produced 0 results, keeping full set to avoid empty response")

        # Мягкий фильтр по вкусам: применяем, но отступаемся если пусто
        flavor_prefilter_applied = False
        if isinstance(filters, dict) and "flavors" in filters:
            ff = filters.get("flavors")
            if isinstance(ff, dict) and ff.get("operator") == "contains" and (ff.get("values") or ff.get("value")):
                tentative = self._apply_universal_filters(source_strains, {"flavors": ff})
                if tentative:
                    logger.info(f"Applied flavor prefilter: {len(source_strains)} -> {len(tentative)}")
                    source_strains = tentative
                    flavor_prefilter_applied = True
                else:
                    logger.info("Flavor prefilter would yield 0 results; skipping to keep broader pool")

        # Мягкий предфильтр по эффектам (desired)
        if isinstance(filters, dict) and "effects" in filters:
            ef = filters.get("effects")
            if isinstance(ef, dict) and ef.get("operator") == "contains" and (ef.get("values") or ef.get("value")):
                tentative = self._apply_universal_filters(source_strains, {"effects": ef})
                if tentative:
                    logger.info(f"Applied effects prefilter: {len(source_strains)} -> {len(tentative)}")
                    source_strains = tentative
                else:
                    logger.info("Effects prefilter would yield 0 results; skipping to keep broader pool")

        # Мягкие числовые предфильтры (THC/CBD/CBG) с операторами порогов
        for num_field in ["thc", "cbd", "cbg"]:
            nf = filters.get(num_field) if isinstance(filters, dict) else None
            if isinstance(nf, dict) and nf.get("operator") in ["gte", ">=", "gt", ">", "lte", "<=", "lt", "<"] and (nf.get("value") is not None):
                tentative = self._apply_universal_filters(source_strains, {num_field: nf})
                if tentative:
                    logger.info(f"Applied numeric prefilter {num_field}: {len(source_strains)} -> {len(tentative)}")
                    source_strains = tentative
                else:
                    logger.info(f"Numeric prefilter {num_field} would yield 0 results; skipping to keep broader pool")
        
        # Проверяем метод scoring
        scoring_method = scoring.get("method", "simple_sort")
        
        if scoring_method == "weighted_priority":
            # Используем медицински-осознанную систему scoring
            scored_strains = self._apply_weighted_priority_scoring(source_strains, filters)
            logger.info(f"Applied weighted priority scoring: {len(scored_strains)} strains scored")
        else:
            # Применяем обычные фильтры
            scored_strains = [(strain, 1.0) for strain in self._apply_universal_filters(source_strains, filters)]
        
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
            # Если сортировка не задана, используем tie-breaker по совпадениям желаемых эффектов
            if not sort_config or not sort_config.get("field"):
                desired = []
                ef_cfg = filters.get("effects") if isinstance(filters, dict) else None
                if isinstance(ef_cfg, dict) and ef_cfg.get("operator") == "contains":
                    desired = [str(v).lower() for v in (ef_cfg.get("values") or ([] if ef_cfg.get("value") is None else [ef_cfg.get("value")]))]
                if desired:
                    def effect_match_count(st: Strain) -> int:
                        vals = [str(v).lower() for v in (st.feelings or [])]
                        return len(set(vals) & set(desired))
                    sorted_strain_list = sorted(strain_list, key=lambda st: effect_match_count(st), reverse=True)
                else:
                    sorted_strain_list = self._apply_universal_sort(strain_list, sort_config)
                
                # Дополнительный семантический буст по ароматам, если запросил пользователь
                fl_cfg = filters.get("flavors") if isinstance(filters, dict) else None
                if isinstance(fl_cfg, dict) and fl_cfg.get("operator") == "contains":
                    targets = [str(v).lower() for v in (fl_cfg.get("values") or ([] if fl_cfg.get("value") is None else [fl_cfg.get("value")]))]
                    if targets:
                        # Если flavor-префильтр не сработал (ничего не отсёк), усиливаем ранжирование по семантике
                        try:
                            sorted_strain_list = self._apply_semantic_flavor_rerank(sorted_strain_list, targets)
                            logger.info("Applied semantic flavor rerank boost")
                        except Exception as e:
                            logger.warning(f"Semantic flavor rerank failed: {e}")
            else:
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
        
        # Если пришли фильтры вместе с сортировкой — сначала применим их к контексту.
        # Если в результате 0 — расширяем поиск по БД с теми же фильтрами и сортируем.
        prefiltered_strains = strains
        incoming_filters = parameters.get("filters")
        if isinstance(incoming_filters, dict) and strains:
            filtered = self._apply_universal_filters(strains, incoming_filters)
            if filtered:
                prefiltered_strains = filtered
            else:
                # Контекст не покрывает новые критерии (например, новая категория Sativa) → поиск в БД
                logger.info("Sort requested with filters but session has 0 matches; expanding search to database")
                searched = self._execute_search_strains([], parameters)
                prefiltered_strains = searched

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
        limit = parameters.get("limit", len(prefiltered_strains) if prefiltered_strains else 0)
        
        logger.info(f"Universal sort: {sort_config}, exclude_invalid={exclude_invalid}")
        
        # Фильтрация invalid значений если требуется
        valid_strains = prefiltered_strains
        if exclude_invalid:
            valid_strains = self._filter_out_invalid_data(
                valid_strains, 
                sort_config["field"], 
                exclude_invalid
            )
            logger.info(f"Filtered invalid: {len(prefiltered_strains)} -> {len(valid_strains)} strains")
        
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
        
        # Применяем универсальные фильтры к контексту
        filtered_strains = self._apply_universal_filters(strains, filters)
        logger.info(f"Filtering result: {len(strains)} -> {len(filtered_strains)} strains")

        # Если 0 — расширяем поиск по БД теми же фильтрами
        if not filtered_strains:
            logger.info("Filter on session returned 0, expanding to database search")
            return self._execute_search_strains([], {"filters": filters, "limit": parameters.get("limit", 5)})
        
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
        
        # Если есть фильтры, сначала фильтруем существующие контекстные сорта теми же фильтрами
        filters = parameters.get("filters", {})
        base_strains = strains
        if isinstance(filters, dict) and filters:
            base_strains = self._apply_universal_filters(strains, filters)
        
        # Объединяем с существующими (отфильтрованными), избегая дубликатов
        existing_ids = {s.id for s in base_strains}
        unique_new_strains = [s for s in new_strains if s.id not in existing_ids]
        combined = base_strains + unique_new_strains
        
        # Применяем сортировку если задана
        sort_cfg = parameters.get("sort")
        if isinstance(sort_cfg, dict) and combined:
            combined = self._apply_universal_sort(combined, {
                "field": sort_cfg.get("field", "thc"),
                "order": sort_cfg.get("order", "desc")
            })
        
        limit = parameters.get("limit", 10)
        logger.info(f"Expand search: base={len(base_strains)}, added={len(unique_new_strains)}")
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
            # Специальный случай: исключающие эффекты передаются отдельным ключом
            if field_name == "effects_exclude":
                if not self._field_matches_filter(strain, "effects", filter_config):
                    return False
                continue
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
        
        # Спец-обработка для ароматов (flavors): синонимы и подстроки
        if field_name == "flavors":
            if operator == "contains":
                # Нормализуем целевые значения с учётом синонимов/языков
                normalized_targets = []
                for t in (target_values or [target_value]):
                    if t is None:
                        continue
                    normalized_targets.extend(get_synonyms("flavors", str(t)))
                return self._flavor_contains_match(field_value, normalized_targets)
            if operator == "not_contains":
                normalized_targets = []
                for t in (target_values or [target_value]):
                    if t is None:
                        continue
                    normalized_targets.extend(get_synonyms("flavors", str(t)))
                return not self._flavor_contains_match(field_value, normalized_targets)

        if field_name in ["effects", "feelings", "negatives", "side_effects", "helps_with", "medical"]:
            # Нормализация и расширение целей по таксономии
            cat = (
                "effects" if field_name in ["effects", "feelings"] else
                "negatives" if field_name in ["negatives", "side_effects"] else
                "helps_with"
            )
            if operator == "contains":
                expanded_targets = []
                for t in (target_values or [target_value]):
                    if t is None:
                        continue
                    expanded_targets.extend(get_synonyms(cat, str(t)))
                return self._contains_match(field_value, expanded_targets)
            if operator == "not_contains":
                expanded_targets = []
                for t in (target_values or [target_value]):
                    if t is None:
                        continue
                    expanded_targets.extend(get_synonyms(cat, str(t)))
                return not self._contains_match(field_value, expanded_targets)
            if operator == "any":
                expanded_targets = []
                for t in (target_values or [target_value]):
                    if t is None:
                        continue
                    expanded_targets.extend(get_synonyms(cat, str(t)))
                return self._any_match(field_value, expanded_targets)

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

    def _flavor_contains_match(self, field_value: Any, targets: List[Any]) -> bool:
        """Проверка совпадений по ароматам с учетом синонимов и подстрок."""
        if not targets:
            return True
        # Нормализуем список ароматов сорта
        if isinstance(field_value, list):
            flavors = [str(v).strip().lower() for v in field_value]
        elif isinstance(field_value, str):
            flavors = [field_value.strip().lower()]
        else:
            return False

        # Цели уже нормализованы через taxonomy
        expanded_set = set(str(t).strip().lower() for t in targets if t)

        # Совпадения по равенству или подстроке в обе стороны
        for fv in flavors:
            for tt in expanded_set:
                if not tt:
                    continue
                if fv == tt or (tt in fv) or (fv in tt):
                    return True
        return False

    # synonyms перенесены в taxonomy
    
    def _get_strain_field_value(self, strain: Strain, field_name: str) -> Any:
        """Универсальное получение значения поля сорта"""
        
        # Прямые поля
        if hasattr(strain, field_name):
            return getattr(strain, field_name)
        
        # Специальные случаи для связанных объектов
        if field_name == "effects" or field_name == "feelings":
            raw = [f.name for f in strain.feelings] if strain.feelings else []
            return normalize_list("effects", raw)
        elif field_name == "helps_with" or field_name == "medical":
            raw = [h.name for h in strain.helps_with] if strain.helps_with else []
            return normalize_list("helps_with", raw)
        elif field_name == "negatives" or field_name == "side_effects":
            raw = [n.name for n in strain.negatives] if strain.negatives else []
            return normalize_list("negatives", raw)
        elif field_name == "flavors":
            raw = [fl.name for fl in strain.flavors] if strain.flavors else []
            return normalize_list("flavors", raw)
        
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

    # ---------- Semantic flavor helpers ----------
    def _apply_semantic_flavor_rerank(self, strains: List[Strain], targets: List[str]) -> List[Strain]:
        """Переранжировать список по косинусной близости ароматов к целевым flavor-токенам.
        Низкая стоимость: кэшируем эмбеддинги, ограничиваемся первыми N вариантами.
        """
        if not strains or not targets:
            return strains
        capped_strains = strains[:120]  # ограничение для производительности
        query_emb = self._get_embedding_cached(" ".join(sorted(set(targets))))
        if not query_emb:
            return strains
        def strain_flavor_score(st: Strain) -> float:
            flavors = [str(fl.name).lower() for fl in (st.flavors or [])]
            if not flavors:
                return 0.0
            sims = []
            for flv in flavors:
                emb = self._get_embedding_cached(f"flavor:{flv}")
                if emb:
                    sims.append(self._cosine_similarity(query_emb, emb))
            return max(sims) if sims else 0.0
        # Считаем скор только для cap и объединяем с остатком
        scored = [(st, strain_flavor_score(st)) for st in capped_strains]
        scored.sort(key=lambda x: x[1], reverse=True)
        ranked = [st for st, _ in scored] + [st for st in strains if st not in set([s for s, _ in scored])]
        return ranked

    def _get_embedding_cached(self, text: str) -> Optional[List[float]]:
        key = text.strip().lower()
        # 1) in-memory
        emb = self._flavor_embedding_cache.get(key)
        if emb is not None:
            return emb
        # 2) persistent redis (stringified list)
        persisted = cache_service.get_persistent(f"emb:flavor:{key}")
        if persisted:
            try:
                emb = [float(x) for x in persisted.split(",")]
                self._flavor_embedding_cache[key] = emb
                return emb
            except Exception:
                pass
        # 3) LLM and cache both
        try:
            emb = self._llm.generate_embedding(key)
            self._flavor_embedding_cache[key] = emb
            try:
                cache_service.set_persistent(f"emb:flavor:{key}", ",".join(str(x) for x in emb), ttl=None)
            except Exception:
                pass
            return emb
        except Exception:
            return None

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x*y for x, y in zip(a, b))
        na = math.sqrt(sum(x*x for x in a))
        nb = math.sqrt(sum(y*y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
    
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
        score_groups: Dict[float, List[tuple]] = {}
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