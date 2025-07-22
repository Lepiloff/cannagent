-- Initialize AI Budtender database with pgvector
-- This script runs when the PostgreSQL container starts

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create strains table (similar to cannamente but simplified for AI Budtender)
CREATE TABLE IF NOT EXISTS strains (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    text_content TEXT,
    description TEXT,
    cbd DECIMAL(5,2),
    thc DECIMAL(5,2),
    cbg DECIMAL(5,2),
    rating DECIMAL(3,2),
    category VARCHAR(100),
    img VARCHAR(255),
    img_alt_text VARCHAR(255),
    active BOOLEAN DEFAULT true,
    top BOOLEAN DEFAULT false,
    main BOOLEAN DEFAULT false,
    is_review BOOLEAN DEFAULT false,
    slug VARCHAR(255),
    embedding vector(1536),  -- OpenAI embedding dimension
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create vector search index
CREATE INDEX IF NOT EXISTS strains_embedding_idx 
ON strains 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create legacy products table for backward compatibility
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for products
CREATE INDEX IF NOT EXISTS products_embedding_idx 
ON products 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Insert sample data
INSERT INTO strains (title, text_content, description, thc, cbd, category, active) VALUES
('Northern Lights', 'Classic indica strain known for its relaxing effects', 'Perfect for evening relaxation and sleep', 18.5, 0.1, 'Indica', true),
('Blue Dream', 'Popular hybrid with balanced effects', 'Great for daytime use and creativity', 17.0, 0.2, 'Hybrid', true),
('Sour Diesel', 'Energizing sativa with diesel aroma', 'Ideal for daytime energy and focus', 20.0, 0.1, 'Sativa', true)
ON CONFLICT (id) DO NOTHING;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_strains_updated_at BEFORE UPDATE ON strains
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column(); 