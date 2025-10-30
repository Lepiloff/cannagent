-- Migration: Initialize Multilingual Database
-- Date: 2025-10-24
-- Purpose: Complete database setup with multilingual support (EN/ES) for AI Budtender
-- Replaces: old 001_add_strain_relations.sql (backed up as .bak)

-- ============================================================================
-- PART 1: Create metadata tables with multilingual support
-- ============================================================================

-- Feelings table with energy categorization and multilingual names
CREATE TABLE IF NOT EXISTS feelings (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,         -- Legacy field
    name_en VARCHAR(50),                      -- English name
    name_es VARCHAR(50),                      -- Spanish name
    energy_type VARCHAR(20) NOT NULL,         -- 'energizing', 'relaxing', 'neutral'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Helps with conditions/medical uses
CREATE TABLE IF NOT EXISTS helps_with (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,        -- Legacy field
    name_en VARCHAR(100),                     -- English name
    name_es VARCHAR(100),                     -- Spanish name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Negative effects
CREATE TABLE IF NOT EXISTS negatives (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,         -- Legacy field
    name_en VARCHAR(50),                      -- English name
    name_es VARCHAR(50),                      -- Spanish name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Flavors/taste profiles
CREATE TABLE IF NOT EXISTS flavors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,         -- Legacy field
    name_en VARCHAR(50),                      -- English name
    name_es VARCHAR(50),                      -- Spanish name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Terpenes with multilingual descriptions (scientific name stays single language)
CREATE TABLE IF NOT EXISTS terpenes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,         -- Scientific name (e.g., "Myrcene")
    description TEXT,                         -- Legacy field
    description_en TEXT,                      -- English description
    description_es TEXT,                      -- Spanish description
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- PART 2: Create junction tables for many-to-many relationships
-- ============================================================================

CREATE TABLE IF NOT EXISTS strain_feelings (
    id SERIAL PRIMARY KEY,
    strain_id INTEGER REFERENCES strains_strain(id) ON DELETE CASCADE,
    feeling_id INTEGER REFERENCES feelings(id) ON DELETE CASCADE,
    UNIQUE(strain_id, feeling_id)
);

CREATE TABLE IF NOT EXISTS strain_helps_with (
    id SERIAL PRIMARY KEY,
    strain_id INTEGER REFERENCES strains_strain(id) ON DELETE CASCADE,
    helps_with_id INTEGER REFERENCES helps_with(id) ON DELETE CASCADE,
    UNIQUE(strain_id, helps_with_id)
);

CREATE TABLE IF NOT EXISTS strain_negatives (
    id SERIAL PRIMARY KEY,
    strain_id INTEGER REFERENCES strains_strain(id) ON DELETE CASCADE,
    negative_id INTEGER REFERENCES negatives(id) ON DELETE CASCADE,
    UNIQUE(strain_id, negative_id)
);

CREATE TABLE IF NOT EXISTS strain_flavors (
    id SERIAL PRIMARY KEY,
    strain_id INTEGER REFERENCES strains_strain(id) ON DELETE CASCADE,
    flavor_id INTEGER REFERENCES flavors(id) ON DELETE CASCADE,
    UNIQUE(strain_id, flavor_id)
);

CREATE TABLE IF NOT EXISTS strain_terpenes (
    id SERIAL PRIMARY KEY,
    strain_id INTEGER REFERENCES strains_strain(id) ON DELETE CASCADE,
    terpene_id INTEGER REFERENCES terpenes(id) ON DELETE CASCADE,
    is_dominant BOOLEAN DEFAULT FALSE,
    UNIQUE(strain_id, terpene_id)
);

-- ============================================================================
-- PART 3: Add multilingual fields and dual embeddings to strains_strain
-- ============================================================================

-- Multilingual content fields
ALTER TABLE strains_strain
    ADD COLUMN IF NOT EXISTS name_en VARCHAR(255),
    ADD COLUMN IF NOT EXISTS name_es VARCHAR(255),
    ADD COLUMN IF NOT EXISTS title_en VARCHAR(255),
    ADD COLUMN IF NOT EXISTS title_es VARCHAR(255),
    ADD COLUMN IF NOT EXISTS description_en TEXT,
    ADD COLUMN IF NOT EXISTS description_es TEXT,
    ADD COLUMN IF NOT EXISTS text_content_en TEXT,
    ADD COLUMN IF NOT EXISTS text_content_es TEXT,
    ADD COLUMN IF NOT EXISTS keywords_en VARCHAR(255),
    ADD COLUMN IF NOT EXISTS keywords_es VARCHAR(255);

-- Dual embeddings for multilingual support
ALTER TABLE strains_strain
    ADD COLUMN IF NOT EXISTS embedding_en vector(1536),
    ADD COLUMN IF NOT EXISTS embedding_es vector(1536);

-- ============================================================================
-- PART 4: Create indexes for performance
-- ============================================================================

-- Junction table indexes
CREATE INDEX IF NOT EXISTS idx_strain_feelings_strain ON strain_feelings(strain_id);
CREATE INDEX IF NOT EXISTS idx_strain_feelings_feeling ON strain_feelings(feeling_id);
CREATE INDEX IF NOT EXISTS idx_strain_helps_with_strain ON strain_helps_with(strain_id);
CREATE INDEX IF NOT EXISTS idx_strain_helps_with_helps ON strain_helps_with(helps_with_id);
CREATE INDEX IF NOT EXISTS idx_strain_negatives_strain ON strain_negatives(strain_id);
CREATE INDEX IF NOT EXISTS idx_strain_negatives_negative ON strain_negatives(negative_id);
CREATE INDEX IF NOT EXISTS idx_strain_flavors_strain ON strain_flavors(strain_id);
CREATE INDEX IF NOT EXISTS idx_strain_flavors_flavor ON strain_flavors(flavor_id);
CREATE INDEX IF NOT EXISTS idx_strain_terpenes_strain ON strain_terpenes(strain_id);
CREATE INDEX IF NOT EXISTS idx_strain_terpenes_terpene ON strain_terpenes(terpene_id);

-- Strain filtering indexes
CREATE INDEX IF NOT EXISTS idx_feelings_energy_type ON feelings(energy_type);
CREATE INDEX IF NOT EXISTS idx_strains_category ON strains_strain(category);
CREATE INDEX IF NOT EXISTS idx_strains_active ON strains_strain(active);

-- Multilingual name indexes
CREATE INDEX IF NOT EXISTS idx_strains_name_en ON strains_strain(name_en);
CREATE INDEX IF NOT EXISTS idx_strains_name_es ON strains_strain(name_es);
CREATE INDEX IF NOT EXISTS idx_feelings_name_en ON feelings(name_en);
CREATE INDEX IF NOT EXISTS idx_feelings_name_es ON feelings(name_es);
CREATE INDEX IF NOT EXISTS idx_helps_with_name_en ON helps_with(name_en);
CREATE INDEX IF NOT EXISTS idx_helps_with_name_es ON helps_with(name_es);
CREATE INDEX IF NOT EXISTS idx_negatives_name_en ON negatives(name_en);
CREATE INDEX IF NOT EXISTS idx_negatives_name_es ON negatives(name_es);
CREATE INDEX IF NOT EXISTS idx_flavors_name_en ON flavors(name_en);
CREATE INDEX IF NOT EXISTS idx_flavors_name_es ON flavors(name_es);

-- Vector search indexes (using ivfflat)
CREATE INDEX IF NOT EXISTS strains_embedding_en_idx
    ON strains_strain USING ivfflat (embedding_en vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS strains_embedding_es_idx
    ON strains_strain USING ivfflat (embedding_es vector_cosine_ops)
    WITH (lists = 100);

-- ============================================================================
-- PART 5: Seed data with multilingual support
-- ============================================================================

-- Insert feelings with EN/ES translations
INSERT INTO feelings (name, name_en, name_es, energy_type) VALUES
    -- Energizing feelings
    ('Energetic', 'Energetic', 'Energético', 'energizing'),
    ('Creative', 'Creative', 'Creativo', 'energizing'),
    ('Focused', 'Focused', 'Concentrado', 'energizing'),
    ('Talkative', 'Talkative', 'Hablador', 'energizing'),
    ('Uplifted', 'Uplifted', 'Animado', 'energizing'),
    ('Euphoric', 'Euphoric', 'Eufórico', 'energizing'),

    -- Relaxing feelings
    ('Sleepy', 'Sleepy', 'Somnoliento', 'relaxing'),
    ('Relaxed', 'Relaxed', 'Relajado', 'relaxing'),
    ('Hungry', 'Hungry', 'Hambriento', 'relaxing'),

    -- Neutral feelings
    ('Happy', 'Happy', 'Feliz', 'neutral'),
    ('Giggly', 'Giggly', 'Risueño', 'neutral'),
    ('Tingly', 'Tingly', 'Hormigueo', 'neutral'),
    ('Aroused', 'Aroused', 'Excitado', 'neutral')
ON CONFLICT (name) DO NOTHING;

-- Insert helps_with conditions with EN/ES translations
INSERT INTO helps_with (name, name_en, name_es) VALUES
    ('Anxiety', 'Anxiety', 'Ansiedad'),
    ('Depression', 'Depression', 'Depresión'),
    ('Fatigue', 'Fatigue', 'Fatiga'),
    ('Headaches', 'Headaches', 'Dolores de cabeza'),
    ('Insomnia', 'Insomnia', 'Insomnio'),
    ('Lack of appetite', 'Lack of appetite', 'Falta de apetito'),
    ('Pain', 'Pain', 'Dolor'),
    ('Stress', 'Stress', 'Estrés')
ON CONFLICT (name) DO NOTHING;

-- Insert negative effects with EN/ES translations
INSERT INTO negatives (name, name_en, name_es) VALUES
    ('Anxious', 'Anxious', 'Ansioso'),
    ('Dry eyes', 'Dry eyes', 'Ojos secos'),
    ('Dry mouth', 'Dry mouth', 'Boca seca'),
    ('Dizzy', 'Dizzy', 'Mareado'),
    ('Headache', 'Headache', 'Dolor de cabeza'),
    ('Paranoid', 'Paranoid', 'Paranoico')
ON CONFLICT (name) DO NOTHING;

-- Insert flavors with EN/ES translations
INSERT INTO flavors (name, name_en, name_es) VALUES
    ('berry', 'Berry', 'Baya'),
    ('citrus', 'Citrus', 'Cítrico'),
    ('diesel', 'Diesel', 'Diesel'),
    ('earthy', 'Earthy', 'Terroso'),
    ('pine', 'Pine', 'Pino'),
    ('sweet', 'Sweet', 'Dulce'),
    ('spicy/herbal', 'Spicy/Herbal', 'Picante/Herbal'),
    ('lemon', 'Lemon', 'Limón'),
    ('grape', 'Grape', 'Uva'),
    ('vanilla', 'Vanilla', 'Vainilla'),
    ('cheese', 'Cheese', 'Queso'),
    ('coffee', 'Coffee', 'Café'),
    ('tropical', 'Tropical', 'Tropical')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- VERIFICATION QUERIES (uncomment for testing)
-- ============================================================================

-- Check that all tables exist
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public'
-- AND table_name IN ('feelings', 'helps_with', 'negatives', 'flavors', 'terpenes',
--                    'strain_feelings', 'strain_helps_with', 'strain_negatives',
--                    'strain_flavors', 'strain_terpenes');

-- Check multilingual columns
-- SELECT column_name, data_type
-- FROM information_schema.columns
-- WHERE table_name IN ('strains_strain', 'feelings', 'helps_with', 'negatives', 'flavors')
-- AND (column_name LIKE '%_en' OR column_name LIKE '%_es' OR column_name LIKE 'embedding_%');

-- Check seed data
-- SELECT name, name_en, name_es FROM feelings;
-- SELECT name, name_en, name_es FROM helps_with;

-- ============================================================================
-- NOTES
-- ============================================================================

-- This migration creates a complete multilingual database structure for AI Budtender.
-- All metadata tables (feelings, helps_with, negatives, flavors) have name_en and name_es fields.
-- Terpenes have description_en and description_es (name is scientific, single language).
-- Strain table has multilingual content fields and dual embeddings (embedding_en, embedding_es).
-- All necessary indexes are created for performance, including vector search indexes.
-- Seed data includes English and Spanish translations for common effects, conditions, and flavors.
