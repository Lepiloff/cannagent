-- Migration: Add structured strain data tables
-- This adds the missing relations from cannamente to support proper filtering

-- Feelings table with energy categorization
CREATE TABLE IF NOT EXISTS feelings (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    energy_type VARCHAR(20) NOT NULL, -- 'energizing', 'relaxing', 'neutral'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Helps with conditions/medical uses
CREATE TABLE IF NOT EXISTS helps_with (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Negative effects
CREATE TABLE IF NOT EXISTS negatives (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Flavors/taste profiles
CREATE TABLE IF NOT EXISTS flavors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Terpenes with descriptions
CREATE TABLE IF NOT EXISTS terpenes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Junction tables for many-to-many relationships
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

-- Add terpene relations
CREATE TABLE IF NOT EXISTS strain_terpenes (
    id SERIAL PRIMARY KEY,
    strain_id INTEGER REFERENCES strains_strain(id) ON DELETE CASCADE,
    terpene_id INTEGER REFERENCES terpenes(id) ON DELETE CASCADE,
    is_dominant BOOLEAN DEFAULT FALSE,
    UNIQUE(strain_id, terpene_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_strain_feelings_strain ON strain_feelings(strain_id);
CREATE INDEX IF NOT EXISTS idx_strain_feelings_feeling ON strain_feelings(feeling_id);
CREATE INDEX IF NOT EXISTS idx_strain_helps_with_strain ON strain_helps_with(strain_id);
CREATE INDEX IF NOT EXISTS idx_strain_helps_with_helps ON strain_helps_with(helps_with_id);
CREATE INDEX IF NOT EXISTS idx_feelings_energy_type ON feelings(energy_type);
CREATE INDEX IF NOT EXISTS idx_strains_category ON strains_strain(category);

-- Insert categorized feelings
INSERT INTO feelings (name, energy_type) VALUES
    -- Energizing feelings
    ('Energetic', 'energizing'),
    ('Creative', 'energizing'),
    ('Focused', 'energizing'),
    ('Talkative', 'energizing'),
    ('Uplifted', 'energizing'),
    ('Euphoric', 'energizing'),
    
    -- Relaxing feelings
    ('Sleepy', 'relaxing'),
    ('Relaxed', 'relaxing'),
    ('Hungry', 'relaxing'),
    
    -- Neutral feelings (can work with both)
    ('Happy', 'neutral'),
    ('Giggly', 'neutral'),
    ('Tingly', 'neutral'),
    ('Aroused', 'neutral')
ON CONFLICT (name) DO NOTHING;

-- Insert helps_with conditions
INSERT INTO helps_with (name) VALUES
    ('Anxiety'),
    ('Depression'),
    ('Fatigue'),
    ('Headaches'),
    ('Insomnia'),
    ('Lack of appetite'),
    ('Pain'),
    ('Stress')
ON CONFLICT (name) DO NOTHING;

-- Insert negative effects
INSERT INTO negatives (name) VALUES
    ('Anxious'),
    ('Dry eyes'),
    ('Dry mouth'),
    ('Dizzy'),
    ('Headache'),
    ('Paranoid')
ON CONFLICT (name) DO NOTHING;

-- Insert common flavors (subset from cannamente)
INSERT INTO flavors (name) VALUES
    ('berry'),
    ('citrus'),
    ('diesel'),
    ('earthy'),
    ('pine'),
    ('sweet'),
    ('spicy/herbal'),
    ('lemon'),
    ('grape'),
    ('vanilla'),
    ('cheese'),
    ('coffee'),
    ('tropical')
ON CONFLICT (name) DO NOTHING;