-- Инициализация базы данных с pgvector расширением
CREATE EXTENSION IF NOT EXISTS vector;

-- Создание индекса для векторного поиска (будет создан автоматически через SQLAlchemy)
-- но можно добавить дополнительные индексы для оптимизации

-- Проверка, что расширение установлено
SELECT * FROM pg_extension WHERE extname = 'vector'; 