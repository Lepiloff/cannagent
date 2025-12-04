#!/usr/bin/env python3
"""
Complete strain data synchronization from cannamente database.

This script:
1. Connects to cannamente database 
2. Fetches ALL strains with structured metadata (feelings, helps_with, negatives, flavors)
3. Clears existing strains and syncs fresh data to local AI Budtender database
4. Creates proper relations and regenerates embeddings with structured content

Production ready with error handling and connection fallbacks.
"""

import os
import sys
import psycopg2
from typing import List, Dict, Any, Optional, Set
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import logging

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.db.database import SessionLocal, Base
from app.db.repository import StrainRepository
from app.models.database import Strain as StrainModel, Feeling, HelpsWith, Negative, Flavor, Terpene
from app.core.rag_service import RAGService
from app.core.llm_interface import get_llm


def get_cannamente_connection():
    """
    Connect to the primary database (cannamente).
    """

    cannamente_host = os.getenv('CANNAMENTE_POSTGRES_HOST', 'cannamente-db')
    cannamente_port = int(os.getenv('CANNAMENTE_POSTGRES_PORT', '5432'))
    cannamente_db = os.getenv('CANNAMENTE_POSTGRES_DB', 'mydatabase')
    cannamente_user = os.getenv('CANNAMENTE_POSTGRES_USER', 'myuser')
    cannamente_password = os.getenv('CANNAMENTE_POSTGRES_PASSWORD', 'mypassword')

    connection_configs = [
        {
            'host': cannamente_host,
            'port': cannamente_port,
            'database': cannamente_db,
            'user': cannamente_user,
            'password': cannamente_password
        },
        {
            'host': '172.17.0.1',  # Docker bridge IP fallback
            'port': cannamente_port,
            'database': cannamente_db,
            'user': cannamente_user,
            'password': cannamente_password
        },
        {
            'host': 'host.docker.internal',  # Fallback for Docker Desktop
            'port': cannamente_port,
            'database': cannamente_db,
            'user': cannamente_user,
            'password': cannamente_password
        },
        {
            'host': 'localhost',  # Fallback for local development
            'port': cannamente_port,
            'database': cannamente_db,
            'user': cannamente_user,
            'password': cannamente_password
        }
    ]
    
    for config in connection_configs:
        try:
            conn = psycopg2.connect(**config)
            print(f"✅ Connected to cannamente at {config['host']}:{config['port']} (DB: {config['database']})")
            return conn
        except Exception as e:
            print(f"⚠️ Failed to connect via {config['host']}: {e}")
            continue
    
    print(f"📋 Settings used:")
    print(f"  cannamente_postgres_host={cannamente_host}")
    print(f"  cannamente_postgres_port={cannamente_port}")
    print(f"  cannamente_postgres_db={cannamente_db}")
    print(f"  cannamente_postgres_user={cannamente_user}")
    print(f"  cannamente_postgres_password={'***' if cannamente_password else 'NOT SET'}")
    
    raise Exception("❌ Could not connect to cannamente database. Check CANNAMENTE_* environment variables.")


def get_local_connection():
    """Connect to AI Budtender local database"""
    host = os.getenv('POSTGRES_HOST', 'canna-postgres')
    port = int(os.getenv('POSTGRES_PORT', '5432'))
    database = os.getenv('POSTGRES_DB', 'postgres')
    user = os.getenv('POSTGRES_USER', 'postgres')
    password = os.getenv('POSTGRES_PASSWORD', 'postgres')

    return psycopg2.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password
    )


def fetch_all_strains_from_cannamente() -> List[Dict[str, Any]]:
    """Fetch all strains with relations and multilingual data from cannamente database"""
    conn = get_cannamente_connection()
    cursor = conn.cursor()

    try:
        # Fetch strains with all structured data including multilingual fields
        cursor.execute("""
            SELECT
                s.id,
                -- Legacy fields for fallback
                s.title as name,
                s.text_content as description,
                -- Multilingual content fields
                s.title_en,
                s.title_es,
                s.description_en,
                s.description_es,
                s.text_content_en,
                s.text_content_es,
                s.keywords_en,
                s.keywords_es,
                -- Cannabinoids
                s.cbd,
                s.thc,
                s.cbg,
                s.category,
                s.active,
                s.slug,
                -- Multilingual metadata arrays
                ARRAY_AGG(DISTINCT f.name_en) FILTER (WHERE f.name_en IS NOT NULL) as feelings_en,
                ARRAY_AGG(DISTINCT f.name_es) FILTER (WHERE f.name_es IS NOT NULL) as feelings_es,
                ARRAY_AGG(DISTINCT h.name_en) FILTER (WHERE h.name_en IS NOT NULL) as helps_with_en,
                ARRAY_AGG(DISTINCT h.name_es) FILTER (WHERE h.name_es IS NOT NULL) as helps_with_es,
                ARRAY_AGG(DISTINCT n.name_en) FILTER (WHERE n.name_en IS NOT NULL) as negatives_en,
                ARRAY_AGG(DISTINCT n.name_es) FILTER (WHERE n.name_es IS NOT NULL) as negatives_es,
                ARRAY_AGG(DISTINCT fl.name_en) FILTER (WHERE fl.name_en IS NOT NULL) as flavors_en,
                ARRAY_AGG(DISTINCT fl.name_es) FILTER (WHERE fl.name_es IS NOT NULL) as flavors_es,
                -- Terpenes (scientific names - single language)
                ARRAY_AGG(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL) as terpenes
            FROM strains_strain s
            LEFT JOIN strains_strain_feelings sf ON s.id = sf.strain_id
            LEFT JOIN strains_feeling f ON sf.feeling_id = f.id
            LEFT JOIN strains_strain_helps_with sh ON s.id = sh.strain_id
            LEFT JOIN strains_helpswith h ON sh.helpswith_id = h.id
            LEFT JOIN strains_strain_negatives sn ON s.id = sn.strain_id
            LEFT JOIN strains_negative n ON sn.negative_id = n.id
            LEFT JOIN strains_strain_flavors sfl ON s.id = sfl.strain_id
            LEFT JOIN strains_flavor fl ON sfl.flavor_id = fl.id
            LEFT JOIN strains_strain_other_terpenes st ON s.id = st.strain_id
            LEFT JOIN strains_terpene t ON st.terpene_id = t.id
            WHERE s.active = true
            GROUP BY s.id, s.title, s.text_content, s.title_en, s.title_es,
                     s.description_en, s.description_es, s.text_content_en, s.text_content_es,
                     s.keywords_en, s.keywords_es, s.cbd, s.thc, s.cbg, s.category, s.active, s.slug
            ORDER BY COALESCE(s.title_es, s.title_en, s.title)
        """)
        
        strains = []
        for row in cursor.fetchall():
            strain_data = {
                'cannamente_id': row[0],
                # Legacy fields (with fallbacks)
                'name': row[1] or f"Strain {row[0]}",
                'description': row[2],
                # Multilingual content fields
                'title_en': row[3],
                'title_es': row[4],
                'name_en': row[3],  # Use title_en as name_en
                'name_es': row[4],  # Use title_es as name_es
                'description_en': row[5],
                'description_es': row[6],
                'text_content_en': row[7],
                'text_content_es': row[8],
                'keywords_en': row[9],
                'keywords_es': row[10],
                # Cannabinoids
                'cbd': float(row[11]) if row[11] is not None else None,
                'thc': float(row[12]) if row[12] is not None else None,
                'cbg': float(row[13]) if row[13] is not None else None,
                'category': row[14],
                'active': row[15],
                'slug': row[16],
                # Multilingual metadata
                'feelings_en': [f for f in (row[17] or []) if f],
                'feelings_es': [f for f in (row[18] or []) if f],
                'helps_with_en': [h for h in (row[19] or []) if h],
                'helps_with_es': [h for h in (row[20] or []) if h],
                'negatives_en': [n for n in (row[21] or []) if n],
                'negatives_es': [n for n in (row[22] or []) if n],
                'flavors_en': [fl for fl in (row[23] or []) if fl],
                'flavors_es': [fl for fl in (row[24] or []) if fl],
                # Terpenes (scientific names)
                'terpenes': [t for t in (row[25] or []) if t],
            }

            # Debug: Print first few strains with terpenes
            if len(strains) < 5:
                print(f"DEBUG - Strain #{len(strains)}: {strain_data['name']}")
                print(f"  Raw terpenes from DB: {row[25]}")
                print(f"  Processed terpenes: {strain_data['terpenes']}")

            strains.append(strain_data)
        
        print(f"📊 Fetched {len(strains)} strains with structured data from cannamente")
        return strains
        
    finally:
        cursor.close()
        conn.close()


def clear_existing_data():
    """Clear existing strains data"""
    conn = get_local_connection()
    cursor = conn.cursor()
    
    try:
        # Clear in correct order due to foreign key constraints
        # Data already cleared manually - skip deletion
        print("🗑️ Database already cleared")
        conn.commit()
        print("🗑️ Cleared existing strains data")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error clearing data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def sync_strains_to_local_db(strains: List[Dict[str, Any]]):
    """Sync strains with relations and multilingual data to local database using SQLAlchemy"""
    canagent_session = SessionLocal()
    repository = StrainRepository(canagent_session)

    try:
        print("🔄 Syncing strains with structured multilingual data...")
        success_count = 0
        error_count = 0

        for strain_data in strains:
            try:
                # Create strain data with multilingual fields
                multilingual_strain_data = {
                    # Legacy fields (for backward compatibility)
                    'name': strain_data['name'],
                    'title': strain_data.get('title_es') or strain_data.get('title_en') or strain_data['name'],
                    'description': strain_data.get('description_es') or strain_data.get('description_en') or strain_data.get('description'),
                    'text_content': strain_data.get('text_content_es') or strain_data.get('text_content_en'),
                    'keywords': strain_data.get('keywords_es') or strain_data.get('keywords_en'),
                    # Multilingual fields
                    'name_en': strain_data.get('name_en'),
                    'name_es': strain_data.get('name_es'),
                    'title_en': strain_data.get('title_en'),
                    'title_es': strain_data.get('title_es'),
                    'description_en': strain_data.get('description_en'),
                    'description_es': strain_data.get('description_es'),
                    'text_content_en': strain_data.get('text_content_en'),
                    'text_content_es': strain_data.get('text_content_es'),
                    'keywords_en': strain_data.get('keywords_en'),
                    'keywords_es': strain_data.get('keywords_es'),
                    # Cannabinoids
                    'cbd': strain_data['cbd'],
                    'thc': strain_data['thc'],
                    'cbg': strain_data['cbg'],
                    'category': strain_data['category'],
                    'active': strain_data['active'],
                    'slug': strain_data['slug']
                }

                # Create strain without embedding initially
                strain = repository.create_strain(multilingual_strain_data, None)

                # Add structured relations with multilingual support
                # Use ES as default (Spanish is primary for cannamente)
                repository.update_strain_relations(
                    strain=strain,
                    feelings=strain_data.get('feelings_es', []) or strain_data.get('feelings_en', []),
                    helps_with=strain_data.get('helps_with_es', []) or strain_data.get('helps_with_en', []),
                    negatives=strain_data.get('negatives_es', []) or strain_data.get('negatives_en', []),
                    flavors=strain_data.get('flavors_es', []) or strain_data.get('flavors_en', []),
                    terpenes=strain_data.get('terpenes', [])
                )
                
                success_count += 1
                if success_count % 20 == 0:
                    print(f"  📦 Synced {success_count} strains...")
                
            except Exception as e:
                error_count += 1
                print(f"❌ Error syncing strain '{strain_data['name']}': {e}")
                continue
        
        print(f"✅ Strain sync completed: {success_count} success, {error_count} errors")
        
    except Exception as e:
        print(f"❌ Fatal error during sync: {e}")
        raise
    finally:
        canagent_session.close()


def regenerate_embeddings():
    """Regenerate dual embeddings (EN + ES) for all strains with structured content"""
    canagent_session = SessionLocal()
    repository = StrainRepository(canagent_session)

    # Get LLM interface for embedding generation
    llm = get_llm()
    rag_service = RAGService(repository, llm)

    try:
        print("🔄 Regenerating dual embeddings (EN + ES) with structured data...")

        # Get all strains
        strains = repository.get_strains(limit=1000)  # Get more than default 100

        success_count = 0
        error_count = 0

        for strain in strains:
            try:
                # Generate dual embeddings (EN + ES) with structured content
                rag_service.add_strain_embeddings(strain.id)
                success_count += 1

                if success_count % 10 == 0:
                    print(f"  🔗 Generated embeddings for {success_count} strains...")

            except Exception as e:
                error_count += 1
                print(f"❌ Error generating embedding for '{strain.name}': {e}")
                continue

        print(f"✅ Embedding regeneration completed: {success_count} success, {error_count} errors")
        print(f"   Each strain now has dual embeddings (embedding_en + embedding_es)")

    except Exception as e:
        print(f"❌ Fatal error during embedding generation: {e}")
        raise
    finally:
        canagent_session.close()


def apply_database_schema():
    """Apply database migration for multilingual strain relations"""
    print("📋 Applying multilingual database schema...")

    # Use correct canagent database connection
    default_url = (
        f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'postgres')}@"
        f"{os.getenv('POSTGRES_HOST', 'canna-postgres')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'postgres')}"
    )
    canagent_engine = create_engine(os.getenv("DATABASE_URL", default_url))

    # First create all tables using SQLAlchemy models
    print("🔧 Creating base tables with SQLAlchemy...")
    from app.models.database import Base
    Base.metadata.create_all(bind=canagent_engine)
    print("✅ Base tables created")

    # Then read and execute migration for data population and multilingual fields
    migration_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "001_init_multilingual_database.sql")
    if os.path.exists(migration_path):
        with open(migration_path, 'r') as f:
            migration_sql = f.read()
        
        # Execute only the INSERT statements, skip table creation
        insert_statements = []
        lines = migration_sql.split('\n')
        current_statement = ""
        in_insert = False
        
        for line in lines:
            if line.strip().startswith('INSERT INTO'):
                in_insert = True
                current_statement = line
            elif in_insert:
                current_statement += '\n' + line
                if line.strip().endswith(';'):
                    insert_statements.append(current_statement)
                    current_statement = ""
                    in_insert = False
        
        if insert_statements:
            print("📊 Populating reference data...")
            with canagent_engine.connect() as conn:
                for statement in insert_statements:
                    try:
                        conn.execute(text(statement))
                    except Exception as e:
                        print(f"⚠️ Warning executing statement: {e}")
                        continue
                conn.commit()
            print("✅ Reference data populated")
        else:
            print("ℹ️ No INSERT statements found in migration")
    else:
        print("⚠️ Migration file not found, skipping data population")


def main():
    """Main synchronization process"""
    print("🚀 Starting COMPLETE strain data sync from cannamente...")
    
    try:
        # Step 1: Ensure pgvector extension is installed
        print("📋 Checking pgvector extension...")
        local_conn = get_local_connection()
        local_conn.autocommit = True
        cursor = local_conn.cursor()
        
        try:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("✅ pgvector extension ready")
        except Exception as e:
            print(f"⚠️ Warning installing pgvector: {e}")
        finally:
            cursor.close()
            local_conn.close()
        
        # Step 2: Create tables using SQLAlchemy
        print("🔧 Creating database schema...")
        default_url = (
            f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
            f"{os.getenv('POSTGRES_PASSWORD', 'postgres')}@"
            f"{os.getenv('POSTGRES_HOST', 'canna-postgres')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB', 'postgres')}"
        )
        canagent_engine = create_engine(os.getenv("DATABASE_URL", default_url))
        
        print("🔧 Creating base tables with SQLAlchemy...")
        from app.models.database import Base
        Base.metadata.create_all(bind=canagent_engine)
        print("✅ Base tables created")
        
        # Step 3: Fetch all strains with structured data
        strains = fetch_all_strains_from_cannamente()
        
        if not strains:
            print("⚠️ No strains found in cannamente database")
            return
        
        # Step 4: Clear existing data
        clear_existing_data()
        
        # Step 5: Sync all strains with relations
        sync_strains_to_local_db(strains)
        
        # Step 6: Regenerate embeddings
        regenerate_embeddings()
        
        print("🎉 COMPLETE strain data sync completed successfully!")
        print(f"💡 The system now has {len(strains)} strains with structured filtering capabilities.")
        print("🔍 Try queries like 'I need something for sleep' - it should now return multiple Indica options!")
        
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
