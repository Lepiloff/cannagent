#!/usr/bin/env python3
"""
Script to initialize pgvector extension in existing cannamente database
"""

import psycopg2
import os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def init_pgvector():
    """Initialize pgvector extension in the database"""
    
    # Database connection parameters
    db_params = {
        'host': 'localhost',  # Connect to host machine
        'port': 5432,
        'database': 'mydatabase',
        'user': 'myuser',
        'password': 'mypassword'
    }
    
    try:
        # Connect to database
        print("Connecting to database...")
        conn = psycopg2.connect(**db_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Create cursor
        cursor = conn.cursor()
        
        # Check if pgvector extension exists
        print("Checking pgvector extension...")
        cursor.execute("SELECT * FROM pg_available_extensions WHERE name = 'vector'")
        extension_exists = cursor.fetchone()
        
        if not extension_exists:
            print("ERROR: pgvector extension is not available in PostgreSQL!")
            print("Please install pgvector extension in your PostgreSQL installation.")
            print("For Ubuntu/Debian: sudo apt-get install postgresql-15-pgvector")
            print("For Docker: Use pgvector/pgvector:pg15 image")
            return False
        
        # Create extension if not exists
        print("Creating pgvector extension...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        
        # Verify extension is installed
        cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
        result = cursor.fetchone()
        
        if result:
            print("✅ pgvector extension successfully installed!")
            
            # Check vector version
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            version = cursor.fetchone()
            if version:
                print(f"pgvector version: {version[0]}")
        else:
            print("❌ Failed to install pgvector extension")
            return False
        
        # Check if strains_strain table exists (Django table from cannamente)
        print("Checking strains_strain table...")
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'strains_strain'
            )
        """)
        strains_table_exists = cursor.fetchone()[0]
        
        if strains_table_exists:
            print("✅ strains_strain table exists (from cannamente Django)")
            
            # Count strains
            cursor.execute("SELECT COUNT(*) FROM strains_strain")
            count = cursor.fetchone()[0]
            print(f"   Strains count: {count}")
            
            # Check if strains_strain table has embedding column
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'strains_strain' 
                AND column_name = 'embedding'
            """)
            embedding_col = cursor.fetchone()
            
            if embedding_col:
                print("✅ strains_strain table has embedding column")
            else:
                print("Adding embedding column to strains_strain table...")
                cursor.execute("""
                    ALTER TABLE strains_strain 
                    ADD COLUMN embedding vector(1536);
                """)
                print("✅ Added embedding column to strains_strain table")
            
            # Create index for vector search on strains_strain
            print("Creating vector search index on strains_strain...")
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS strains_strain_embedding_idx 
                ON strains_strain 
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            print("✅ Created vector search index on strains_strain")
            
            # Show sample strains
            if count > 0:
                cursor.execute("SELECT name, category, thc, cbd FROM strains_strain LIMIT 3")
                sample_strains = cursor.fetchall()
                print("   Sample strains:")
                for strain in sample_strains:
                    print(f"     - {strain[0]} ({strain[1]}) - THC: {strain[2]}%, CBD: {strain[3]}%")
            
        else:
            print("❌ strains_strain table does not exist")
            print("   Make sure cannamente project is properly initialized")
            return False
        
        # Create legacy products table if not exists (for backward compatibility)
        print("Creating legacy products table...")
        create_products_table_sql = """
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            embedding vector(1536),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_products_table_sql)
        
        # Create index for vector search on products
        print("Creating vector search index on products...")
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS products_embedding_idx 
        ON products 
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
        """)
        
        print("✅ Database initialization completed successfully!")
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    print("🚀 Initializing pgvector in cannamente database...")
    success = init_pgvector()
    if success:
        print("✅ All done! You can now run the AI Budtender service.")
    else:
        print("❌ Initialization failed. Please check the errors above.") 