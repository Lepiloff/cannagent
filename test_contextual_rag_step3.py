#!/usr/bin/env python3
"""
Тест для ШАГ 3: Enhanced RAG Service с контекстом
Критерии завершения шага:
- Follow-up запросы работают с существующими рекомендациями
- Reset функциональность очищает контекст
- Query types обрабатываются по-разному  
- API возвращает расширенные метаданные
"""

import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import Mock
from app.core.optimized_rag_service import OptimizedContextualRAGService
from app.models.session import ConversationSession, UnifiedAnalysis
from app.models.schemas import Strain
from app.core.intent_detection import IntentType
from app.db.repository import StrainRepository


def create_mock_strain(strain_id: int, name: str, thc: float = 15.0, category: str = "Hybrid"):
    """Создание мок-объекта сорта для тестирования"""
    mock_strain = Mock()
    mock_strain.id = strain_id
    mock_strain.name = name
    mock_strain.thc = thc
    mock_strain.cbd = 5.0
    mock_strain.cbg = 1.0
    mock_strain.category = category
    mock_strain.slug = name.lower().replace(' ', '-')
    
    # Mock feelings
    feeling1 = Mock()
    feeling1.name = "Relaxed"
    feeling2 = Mock()
    feeling2.name = "Happy"
    mock_strain.feelings = [feeling1, feeling2]
    
    # Mock helps_with
    help1 = Mock()
    help1.name = "Stress"
    help2 = Mock()
    help2.name = "Pain"
    mock_strain.helps_with = [help1, help2]
    
    # Mock negatives
    neg1 = Mock()
    neg1.name = "Dry mouth"
    mock_strain.negatives = [neg1]
    
    # Mock flavors
    flavor1 = Mock()
    flavor1.name = "earthy"
    flavor2 = Mock()
    flavor2.name = "sweet"
    mock_strain.flavors = [flavor1, flavor2]
    
    return mock_strain


def create_mock_repository() -> Mock:
    """Создание мок-репозитория для тестирования"""
    repository = Mock()
    
    # Мок сорта для тестирования
    mock_strains = [
        create_mock_strain(1, "Northern Lights", 18.0, "Indica"),
        create_mock_strain(2, "Sour Diesel", 22.0, "Sativa"),  
        create_mock_strain(3, "Blue Dream", 17.0, "Hybrid")
    ]
    
    repository.get_strain_with_relations.side_effect = lambda strain_id: next(
        (s for s in mock_strains if s.id == strain_id), None
    )
    
    repository.search_strains_with_filters.return_value = mock_strains[:2]
    repository.search_strains_by_name.return_value = mock_strains[:1]
    
    return repository


def test_new_search_query():
    """Тест 1: Новый поиск (new_search)"""
    print("🔵 Тест 1: New Search Query")
    
    # Создаем мок-зависимости
    repository = create_mock_repository()
    rag_service = OptimizedContextualRAGService(repository)
    
    # Мокируем session manager чтобы избежать Redis
    mock_session = ConversationSession.create_new()
    rag_service.session_manager = Mock()
    rag_service.session_manager.get_or_restore_session.return_value = mock_session
    rag_service.session_manager.save_session_with_backup.return_value = None
    
    # Мокируем unified_processor для возврата контролируемого анализа
    rag_service.unified_processor.analyze_complete = Mock(return_value=UnifiedAnalysis(
        detected_language="es",
        query_type="new_search", 
        confidence=0.9,
        criteria={
            "effects": {"desired": ["Sleepy", "Relaxed"]},
            "potency": {"thc": "higher"}
        },
        action_needed="filter",
        response_text="Te recomiendo estas variedades indica para dormir.",
        original_query="necesito algo para dormir"
    ))
    
    # Выполнение теста
    response = rag_service.process_contextual_query(
        query="necesito algo para dormir",
        session_id=None
    )
    
    # Проверки
    assert response.query_type == "new_search"
    assert response.language == "es" 
    assert response.confidence == 0.9
    assert response.session_id is not None
    assert len(response.recommended_strains) > 0
    assert response.is_fallback is False
    
    print(f"  ✅ Новый поиск: {response.query_type}, язык: {response.language}")
    print(f"  ✅ Найдено сортов: {len(response.recommended_strains)}")
    print(f"  ✅ Session ID создан: {response.session_id[:8]}...")


def test_follow_up_query():
    """Тест 2: Follow-up запрос с существующим контекстом"""
    print("\n🔵 Тест 2: Follow-up Query")
    
    repository = create_mock_repository()
    rag_service = OptimizedContextualRAGService(repository)
    
    # Создаем сессию с существующими рекомендациями
    session = ConversationSession.create_new()
    session.add_strain_recommendation([1, 2, 3])  # Предыдущие рекомендации
    session.detected_language = "es"
    
    # Мокируем session manager для возврата нашей сессии
    rag_service.session_manager = Mock()
    rag_service.session_manager.get_or_restore_session.return_value = session
    rag_service.session_manager.save_session_with_backup.return_value = None
    
    # Мокируем анализ для follow-up
    rag_service.unified_processor.analyze_complete = Mock(return_value=UnifiedAnalysis(
        detected_language="es",
        query_type="follow_up",
        confidence=0.85,
        criteria={
            "potency": {"thc": "higher"}
        },
        action_needed="filter",
        response_text="De los que te recomendé, el más fuerte es...",
        original_query="¿cuál es más fuerte?"
    ))
    
    # Выполнение теста  
    response = rag_service.process_contextual_query(
        query="¿cuál es más fuerte?",
        session_id=session.session_id
    )
    
    # Проверки
    assert response.query_type == "follow_up"
    assert response.session_id == session.session_id
    assert len(response.recommended_strains) > 0  # Работает с существующими
    
    print(f"  ✅ Follow-up запрос: {response.query_type}")
    print(f"  ✅ Использует существующую сессию: {response.session_id[:8]}...")
    print(f"  ✅ Обработано существующих сортов: {len(response.recommended_strains)}")


def test_reset_functionality():
    """Тест 3: Reset функциональность"""
    print("\n🔵 Тест 3: Reset Functionality")
    
    repository = create_mock_repository()
    rag_service = OptimizedContextualRAGService(repository)
    
    # Создаем сессию с богатым контекстом
    session = ConversationSession.create_new()
    session.add_strain_recommendation([1, 2, 3])
    session.current_topic = IntentType.SLEEP
    session.user_preferences = {'effects': {'Sleepy', 'Relaxed'}}
    session.add_conversation_entry("test", "response", IntentType.SLEEP)
    
    rag_service.session_manager = Mock()
    rag_service.session_manager.get_or_restore_session.return_value = session
    rag_service.session_manager.save_session_with_backup.return_value = None
    
    # Мокируем анализ reset
    rag_service.unified_processor.analyze_complete = Mock(return_value=UnifiedAnalysis(
        detected_language="es",
        query_type="reset",
        confidence=1.0,
        action_needed="reset",
        response_text="Perfecto, empecemos de nuevo.",
        original_query="empezar de nuevo"
    ))
    
    # Выполнение теста
    response = rag_service.process_contextual_query(
        query="empezar de nuevo",
        session_id=session.session_id
    )
    
    # Проверки
    assert response.query_type == "reset"
    assert len(response.recommended_strains) == 0  # Нет рекомендаций при reset
    assert response.confidence == 1.0
    assert len(response.quick_actions) > 0  # Должны быть предложения для нового поиска
    
    # Проверка очистки сессии
    assert len(session.recommended_strains_history) == 0
    assert len(session.conversation_history) == 0
    assert session.current_topic is None
    
    print(f"  ✅ Reset выполнен: {response.query_type}")
    print(f"  ✅ Контекст очищен: история сортов = {len(session.recommended_strains_history)}")
    print(f"  ✅ Quick actions для нового поиска: {response.quick_actions}")


def test_no_context_handling():
    """Тест 4: Обработка follow-up без контекста"""
    print("\n🔵 Тест 4: No Context Handling")
    
    repository = create_mock_repository()
    rag_service = OptimizedContextualRAGService(repository)
    
    # Пустая сессия без предыдущих рекомендаций
    empty_session = ConversationSession.create_new()
    
    rag_service.session_manager.get_or_restore_session = Mock(return_value=empty_session)
    rag_service.session_manager.save_session_with_backup = Mock()
    
    # Мокируем анализ follow-up
    rag_service.unified_processor.analyze_complete = Mock(return_value=UnifiedAnalysis(
        detected_language="en",
        query_type="follow_up",
        confidence=0.7,
        action_needed="clarify",
        response_text="Which strains would you like me to compare?",
        original_query="which is better?"
    ))
    
    # Выполнение теста
    response = rag_service.process_contextual_query(
        query="which is better?",
        session_id=empty_session.session_id
    )
    
    # Проверки
    assert response.query_type == "clarification"  # Должно быть изменено на clarification
    assert response.detected_intent == "no_context"
    assert len(response.recommended_strains) == 0
    assert "previous strains" in response.response or "variedades anteriores" in response.response
    
    print(f"  ✅ No context обработан: {response.query_type}")
    print(f"  ✅ Detected intent: {response.detected_intent}")
    print(f"  ✅ Подходящий ответ: содержит упоминание о предыдущих сортах")


def test_conflict_resolution():
    """Тест 5: Разрешение конфликтов в критериях"""
    print("\n🔵 Тест 5: Conflict Resolution")
    
    repository = create_mock_repository()
    rag_service = OptimizedContextualRAGService(repository)
    
    session = ConversationSession.create_new()
    rag_service.session_manager = Mock()
    rag_service.session_manager.get_or_restore_session.return_value = session
    rag_service.session_manager.save_session_with_backup.return_value = None
    
    # Анализ с конфликтующими критериями
    conflicting_analysis = UnifiedAnalysis(
        detected_language="es",
        query_type="new_search",
        confidence=0.8,
        criteria={
            "effects": {
                "desired": ["Sleepy", "Energetic"],  # Конфликт!
                "avoid": ["Sleepy"]  # Еще один конфликт!
            }
        },
        action_needed="filter",
        response_text="Te ayudo con eso...",
        original_query="necesito algo relajante pero energético"
    )
    
    rag_service.unified_processor.analyze_complete = Mock(return_value=conflicting_analysis)
    
    # Выполнение теста
    response = rag_service.process_contextual_query(
        query="necesito algo relajante pero energético",
        session_id=session.session_id
    )
    
    # Проверки
    assert response.warnings is not None
    assert len(response.warnings) > 0
    assert any("conflict" in warning.lower() for warning in response.warnings)
    
    print(f"  ✅ Конфликты детектированы: {len(response.warnings)}")
    print(f"  ✅ Первый конфликт: {response.warnings[0]}")


def test_session_updates():
    """Тест 6: Обновление сессии"""
    print("\n🔵 Тест 6: Session Updates")
    
    repository = create_mock_repository()
    rag_service = OptimizedContextualRAGService(repository)
    
    session = ConversationSession.create_new()
    original_activity = session.last_activity
    
    rag_service.session_manager = Mock()
    rag_service.session_manager.get_or_restore_session.return_value = session
    rag_service.session_manager.save_session_with_backup.return_value = None
    
    rag_service.unified_processor.analyze_complete = Mock(return_value=UnifiedAnalysis(
        detected_language="en",
        query_type="new_search",
        confidence=0.9,
        criteria={
            "effects": {"desired": ["Creative", "Focused"]}
        },
        action_needed="filter",
        response_text="Here are creative strains...",
        original_query="I need something for creativity"
    ))
    
    # Выполнение теста
    response = rag_service.process_contextual_query(
        query="I need something for creativity",
        session_id=session.session_id
    )
    
    # Проверки обновления сессии
    assert session.detected_language == "en"  # Язык обновлен
    assert session.last_activity > original_activity  # Время активности обновлено
    assert len(session.conversation_history) > 0  # Добавлена запись
    assert session.current_topic == IntentType.CREATIVITY  # Тема определена
    assert "preferred_effects" in session.user_preferences  # Предпочтения обновлены
    
    print(f"  ✅ Язык обновлен: {session.detected_language}")
    print(f"  ✅ Тема установлена: {session.current_topic.value if session.current_topic else None}")
    print(f"  ✅ Предпочтения: {list(session.user_preferences.keys())}")
    print(f"  ✅ История: {len(session.conversation_history)} записей")


def run_all_tests():
    """Запуск всех тестов для ШАГ 3"""
    print("🚀 ТЕСТЫ ШАГ 3: Enhanced RAG Service с контекстом")
    print("=" * 70)
    
    try:
        # Тест 1: New search
        test_new_search_query()
        
        # Тест 2: Follow-up
        test_follow_up_query()
        
        # Тест 3: Reset
        test_reset_functionality()
        
        # Тест 4: No context
        test_no_context_handling()
        
        # Тест 5: Conflicts
        test_conflict_resolution()
        
        # Тест 6: Session updates
        test_session_updates()
        
        print("\n" + "=" * 70)
        print("🎉 ВСЕ ТЕСТЫ ШАГ 3 ПРОЙДЕНЫ УСПЕШНО!")
        print()
        print("✅ Критерии завершения ШАГ 3:")
        print("  • New search работает с созданием новой сессии")
        print("  • Follow-up запросы обрабатывают существующий контекст")
        print("  • Reset функциональность очищает контекст корректно")
        print("  • No context edge case обрабатывается gracefully")
        print("  • Конфликты в критериях разрешаются и предупреждают")
        print("  • Сессии обновляются с новыми данными и предпочтениями")
        print()
        print("🔄 Готов к переходу на ШАГ 4: Embedding Cache System")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()