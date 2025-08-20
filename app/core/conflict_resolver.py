import logging
from typing import Dict, Any, List, Tuple, Set

logger = logging.getLogger(__name__)


class CriteriaConflictResolver:
    """Разрешение конфликтов в критериях поиска"""
    
    def __init__(self):
        # Определение конфликтующих эффектов
        self.CONFLICTING_EFFECTS = [
            ({'Sleepy', 'Relaxed', 'Couch Lock'}, {'Energetic', 'Uplifted', 'Talkative'}),
            ({'Focused', 'Alert'}, {'Giggly', 'Tingly', 'Euphoric'}),
            ({'Hungry', 'Appetite'}, {'Appetite Loss', 'Nausea'}),
            ({'Calm', 'Peaceful'}, {'Anxious', 'Paranoid'}),
            ({'Creative', 'Inspired'}, {'Sleepy', 'Couch Lock'})
        ]
        
        # Медицинские условия и их конфликты
        self.MEDICAL_CONFLICTS = [
            ({'Insomnia', 'Sleep Disorders'}, {'ADHD', 'Fatigue'}),
            ({'Anxiety', 'Stress'}, {'Depression'}),  # Может быть overlap, но разные подходы
            ({'Chronic Pain', 'Inflammation'}, {'High Blood Pressure'})  # Осторожность с потенцией
        ]
        
        # Контекстные ключевые слова для определения приоритета
        self.CONTEXT_PRIORITIES = {
            'sleep': ['dormir', 'sueño', 'insomnia', 'sleep', 'night', 'rest'],
            'work': ['trabajar', 'trabajo', 'work', 'focus', 'concentrate', 'productivity'],
            'social': ['social', 'party', 'friends', 'amigos', 'fiesta'],
            'medical': ['dolor', 'pain', 'medicine', 'treatment', 'therapy', 'chronic']
        }
    
    def resolve_conflicts(
        self,
        criteria: Dict[str, Any],
        context: str
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Разрешение конфликтов с предупреждениями"""
        
        if not criteria:
            return criteria, []
        
        conflicts = []
        resolved_criteria = criteria.copy()
        
        # 1. Разрешение конфликтов в эффектах
        if 'effects' in criteria:
            resolved_effects, effect_conflicts = self._resolve_effect_conflicts(
                criteria['effects'], context
            )
            resolved_criteria['effects'] = resolved_effects
            conflicts.extend(effect_conflicts)
        
        # 2. Разрешение медицинских конфликтов
        if 'medical_conditions' in criteria:
            resolved_medical, medical_conflicts = self._resolve_medical_conflicts(
                criteria['medical_conditions'], context
            )
            resolved_criteria['medical_conditions'] = resolved_medical
            conflicts.extend(medical_conflicts)
        
        # 3. Разрешение конфликтов потенциальности
        if 'potency' in criteria and 'medical_conditions' in criteria:
            potency_conflicts = self._check_potency_medical_conflicts(
                criteria['potency'], criteria['medical_conditions']
            )
            conflicts.extend(potency_conflicts)
        
        # 4. Сохранение информации о конфликтах в критериях
        if conflicts:
            resolved_criteria['conflicts_detected'] = conflicts
        
        logger.info(f"Conflict resolution completed. Found {len(conflicts)} conflicts.")
        
        return resolved_criteria, conflicts
    
    def _resolve_effect_conflicts(
        self, 
        effects: Dict[str, Any], 
        context: str
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Разрешение конфликтов в эффектах"""
        
        conflicts = []
        resolved_effects = effects.copy()
        
        desired = set(effects.get('desired', []))
        avoid = set(effects.get('avoid', []))
        
        # 1. Проверка прямых конфликтов (желаю и избегаю одновременно)
        direct_conflicts = desired & avoid
        if direct_conflicts:
            conflicts.append(f"Direct conflict: wanting and avoiding {list(direct_conflicts)}")
            # Приоритет на desired - убираем из avoid
            resolved_effects['avoid'] = list(avoid - direct_conflicts)
            logger.warning(f"Resolved direct conflict: removed {direct_conflicts} from avoid list")
        
        # 2. Проверка логических конфликтов (противоположные эффекты)
        for group1, group2 in self.CONFLICTING_EFFECTS:
            conflict1 = desired & group1
            conflict2 = desired & group2
            
            if conflict1 and conflict2:
                conflicts.append(f"Logical conflict: {list(conflict1)} vs {list(conflict2)}")
                
                # Определение приоритета на основе контекста
                priority_effect = self._determine_effect_priority(
                    context, conflict1, conflict2
                )
                
                if priority_effect:
                    # Оставляем только приоритетный эффект
                    if priority_effect in conflict1:
                        resolved_effects['desired'] = list(
                            (desired - conflict2) | {priority_effect}
                        )
                        resolved_effects['avoid'] = list(
                            set(resolved_effects.get('avoid', [])) | conflict2
                        )
                    else:
                        resolved_effects['desired'] = list(
                            (desired - conflict1) | {priority_effect}
                        )
                        resolved_effects['avoid'] = list(
                            set(resolved_effects.get('avoid', [])) | conflict1
                        )
                    
                    resolved_effects['priority'] = priority_effect
                    logger.info(f"Resolved logical conflict with priority: {priority_effect}")
        
        return resolved_effects, conflicts
    
    def _resolve_medical_conflicts(
        self, 
        medical_conditions: List[str], 
        context: str
    ) -> Tuple[List[str], List[str]]:
        """Разрешение медицинских конфликтов"""
        
        conflicts = []
        resolved_conditions = medical_conditions.copy()
        
        conditions_set = set(medical_conditions)
        
        # Проверка медицинских конфликтов
        for group1, group2 in self.MEDICAL_CONFLICTS:
            conflict1 = conditions_set & group1
            conflict2 = conditions_set & group2
            
            if conflict1 and conflict2:
                conflicts.append(f"Medical conflict: {list(conflict1)} and {list(conflict2)} may require different approaches")
                # Не убираем условия, но предупреждаем
                logger.warning(f"Medical conflict detected: {conflict1} vs {conflict2}")
        
        return resolved_conditions, conflicts
    
    def _check_potency_medical_conflicts(
        self, 
        potency: Dict[str, Any], 
        medical_conditions: List[str]
    ) -> List[str]:
        """Проверка конфликтов между потенциальностью и медицинскими условиями"""
        
        conflicts = []
        
        if not potency.get('thc'):
            return conflicts
        
        high_thc_caution = {'Anxiety', 'Paranoia', 'High Blood Pressure', 'Heart Conditions'}
        sensitive_conditions = set(medical_conditions) & high_thc_caution
        
        if potency['thc'] == 'higher' and sensitive_conditions:
            conflicts.append(
                f"Caution: High THC may worsen {list(sensitive_conditions)}. Consider lower potency."
            )
        
        return conflicts
    
    def _determine_effect_priority(
        self, 
        context: str, 
        group1: Set[str], 
        group2: Set[str]
    ) -> str:
        """Определение приоритета на основе контекста"""
        
        context_lower = context.lower()
        
        # Анализ контекста для определения приоритета
        context_scores = {}
        
        for priority_type, keywords in self.CONTEXT_PRIORITIES.items():
            score = sum(1 for keyword in keywords if keyword in context_lower)
            if score > 0:
                context_scores[priority_type] = score
        
        # Определение приоритета на основе контекста
        if context_scores:
            top_context = max(context_scores.keys(), key=lambda k: context_scores[k])
            
            if top_context == 'sleep':
                # Приоритет релаксации
                sleep_effects = {'Sleepy', 'Relaxed', 'Couch Lock'}
                priority_candidates = (group1 | group2) & sleep_effects
                if priority_candidates:
                    return list(priority_candidates)[0]
            
            elif top_context == 'work':
                # Приоритет фокуса
                focus_effects = {'Focused', 'Alert', 'Energetic'}
                priority_candidates = (group1 | group2) & focus_effects
                if priority_candidates:
                    return list(priority_candidates)[0]
            
            elif top_context == 'social':
                # Приоритет социальности
                social_effects = {'Talkative', 'Euphoric', 'Happy'}
                priority_candidates = (group1 | group2) & social_effects
                if priority_candidates:
                    return list(priority_candidates)[0]
        
        # По умолчанию берем первый упомянутый
        return list(group1)[0] if group1 else list(group2)[0] if group2 else ""
    
    def validate_criteria_consistency(self, criteria: Dict[str, Any]) -> List[str]:
        """Валидация общей консистентности критериев"""
        
        warnings = []
        
        if not criteria:
            return warnings
        
        # Проверка на слишком много критериев
        desired_effects = criteria.get('effects', {}).get('desired', [])
        if len(desired_effects) > 4:
            warnings.append("Too many desired effects may limit results. Consider prioritizing.")
        
        # Проверка на слишком строгие фильтры
        avoid_effects = criteria.get('effects', {}).get('avoid', [])
        if len(avoid_effects) > 3:
            warnings.append("Too many avoided effects may severely limit results.")
        
        # Проверка медицинских условий
        medical_conditions = criteria.get('medical_conditions', [])
        if len(medical_conditions) > 2:
            warnings.append("Multiple medical conditions detected. Results may be limited.")
        
        return warnings