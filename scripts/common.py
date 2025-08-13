"""
Common functions for database synchronization scripts.

This module provides shared functionality for both initial database setup
and incremental synchronization with the cannamente database.
"""

import os
import sys
import time
import psycopg2
from datetime import datetime
from typing import Optional, Dict, List, Any
from sqlalchemy import create_engine, text

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import Base


def validate_environment():
    """Validate required environment variables for production deployment"""
    required_vars = [
        'CANNAMENTE_POSTGRES_HOST',
        'CANNAMENTE_POSTGRES_DB', 
        'CANNAMENTE_POSTGRES_USER',
        'CANNAMENTE_POSTGRES_PASSWORD'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        env_type = os.getenv('ENVIRONMENT', 'development').lower()
        if env_type == 'production':
            raise ValueError(f"Missing required environment variables for production: {', '.join(missing_vars)}")
        else:
            print(f"⚠️ Missing environment variables (OK for development): {', '.join(missing_vars)}")
    
    return True


def get_cannamente_connection(max_retries: int = 3, retry_delay: int = 5) -> Optional[psycopg2.extensions.connection]:
    """
    Connect to cannamente database with retry logic and graceful failure handling.
    
    Args:
        max_retries: Maximum number of connection attempts
        retry_delay: Delay in seconds between retries
        
    Returns:
        Database connection or None if all attempts fail
    """
    # Get connection parameters from environment variables
    cannamente_host = os.getenv('CANNAMENTE_POSTGRES_HOST')
    cannamente_port = int(os.getenv('CANNAMENTE_POSTGRES_PORT', '5432'))
    cannamente_db = os.getenv('CANNAMENTE_POSTGRES_DB')
    cannamente_user = os.getenv('CANNAMENTE_POSTGRES_USER')
    cannamente_password = os.getenv('CANNAMENTE_POSTGRES_PASSWORD')
    
    # Primary connection config
    config = {
        'host': cannamente_host,
        'port': cannamente_port,
        'database': cannamente_db,
        'user': cannamente_user,
        'password': cannamente_password,
        'connect_timeout': 10
    }
    
    # Development fallback hosts (only if not in production)
    fallback_hosts = []
    env_type = os.getenv('ENVIRONMENT', 'development').lower()
    if env_type != 'production':
        fallback_hosts = ['172.17.0.1', 'host.docker.internal', 'localhost']
        print("🔧 Development mode: will try fallback hosts if primary fails")
    
    # Build list of configs to try
    all_configs = [config] if config['host'] else []
    
    # Add fallback configs for development
    for fallback_host in fallback_hosts:
        fallback_config = {
            'host': fallback_host,
            'port': cannamente_port,
            'database': cannamente_db or 'mydatabase',
            'user': cannamente_user or 'myuser', 
            'password': cannamente_password or 'mypassword',
            'connect_timeout': 10
        }
        all_configs.append(fallback_config)
    
    if not all_configs:
        print("❌ No connection configurations available")
        return None
    
    # Try each configuration with retry logic
    for config_idx, config in enumerate(all_configs, 1):
        print(f"🔄 Trying connection {config_idx}/{len(all_configs)}: {config['host']}:{config['port']}")
        
        for attempt in range(1, max_retries + 1):
            try:
                conn = psycopg2.connect(**config)
                print(f"✅ Connected to cannamente at {config['host']}:{config['port']} (DB: {config['database']}) on attempt {attempt}")
                return conn
                
            except psycopg2.OperationalError as e:
                if attempt < max_retries:
                    print(f"❌ Attempt {attempt} failed: {e}")
                    print(f"⏳ Waiting {retry_delay} seconds before retry...")
                    time.sleep(retry_delay)
                else:
                    print(f"❌ All {max_retries} attempts failed for {config['host']}")
            except Exception as e:
                print(f"❌ Unexpected error connecting to {config['host']}: {e}")
                break  # Don't retry on unexpected errors
    
    print("❌ Could not connect to cannamente database with any configuration")
    return None


def get_local_connection() -> psycopg2.extensions.connection:
    """Connect to local AI Budtender database"""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'ai_budtender'),
        user=os.getenv('POSTGRES_USER', 'ai_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'ai_password')
    )


def ensure_pgvector_extension():
    """Ensure pgvector extension is installed in local database"""
    print("📋 Checking pgvector extension...")
    
    try:
        local_conn = get_local_connection()
        local_conn.autocommit = True
        cursor = local_conn.cursor()
        
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("✅ pgvector extension ready")
        
        cursor.close()
        local_conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error installing pgvector: {e}")
        return False


def create_database_schema():
    """Create database schema using SQLAlchemy models"""
    print("🔧 Creating database schema...")
    
    try:
        default_url = "postgresql://ai_user:ai_password@db:5432/ai_budtender" 
        engine = create_engine(os.getenv("DATABASE_URL", default_url))
        
        Base.metadata.create_all(bind=engine)
        print("✅ Database schema created")
        return True
        
    except Exception as e:
        print(f"❌ Error creating database schema: {e}")
        return False


def record_sync_metadata(sync_type: str, strains_synced: int, success: bool = True):
    """Record synchronization metadata for tracking"""
    try:
        local_conn = get_local_connection()
        cursor = local_conn.cursor()
        
        # Create sync_metadata table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_metadata (
                id SERIAL PRIMARY KEY,
                sync_type VARCHAR(20) NOT NULL,
                strains_synced INTEGER NOT NULL,
                success BOOLEAN NOT NULL DEFAULT true,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT
            );
        """)
        
        # Insert sync record
        cursor.execute("""
            INSERT INTO sync_metadata (sync_type, strains_synced, success, started_at)
            VALUES (%s, %s, %s, %s)
        """, (sync_type, strains_synced, success, datetime.now()))
        
        local_conn.commit()
        cursor.close()
        local_conn.close()
        
        print(f"📊 Recorded sync metadata: {sync_type} - {strains_synced} strains")
        
    except Exception as e:
        print(f"⚠️ Could not record sync metadata: {e}")


def get_last_sync_time() -> Optional[datetime]:
    """Get the timestamp of the last successful synchronization"""
    try:
        local_conn = get_local_connection()
        cursor = local_conn.cursor()
        
        cursor.execute("""
            SELECT completed_at FROM sync_metadata 
            WHERE success = true 
            ORDER BY completed_at DESC 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        cursor.close()
        local_conn.close()
        
        return result[0] if result else None
        
    except psycopg2.errors.UndefinedTable:
        # Table doesn't exist yet - this is first sync
        return None
    except Exception as e:
        print(f"⚠️ Could not get last sync time: {e}")
        return None


def fetch_strains_from_cannamente(since: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Fetch strains from cannamente database.
    
    Args:
        since: If provided, only fetch strains updated after this timestamp
        
    Returns:
        List of strain dictionaries
    """
    conn = get_cannamente_connection()
    if not conn:
        print("⚠️ Cannamente database unavailable - graceful failure mode")
        return []
    
    try:
        cursor = conn.cursor()
        
        # Build query based on whether we want incremental or full sync
        if since:
            print(f"🔄 Fetching strains updated since {since}")
            query = """
                SELECT id, name, title, text_content, description, keywords,
                       cbd, thc, cbg, rating, category, img, img_alt_text, 
                       active, top, main, is_review, slug, created_at, updated_at
                FROM strains_strain 
                WHERE active = true 
                  AND (updated_at > %s OR created_at > %s)
                ORDER BY updated_at DESC
            """
            cursor.execute(query, (since, since))
        else:
            print("🔄 Fetching all active strains")
            query = """
                SELECT id, name, title, text_content, description, keywords,
                       cbd, thc, cbg, rating, category, img, img_alt_text, 
                       active, top, main, is_review, slug, created_at, updated_at
                FROM strains_strain 
                WHERE active = true 
                ORDER BY id
            """
            cursor.execute(query)
        
        columns = [desc[0] for desc in cursor.description]
        strains = []
        
        for row in cursor.fetchall():
            strain_data = dict(zip(columns, row))
            
            # Fetch related data for this strain
            strain_id = strain_data['id']
            
            # Fetch feelings
            cursor.execute("""
                SELECT sf.name FROM strains_feeling sf
                JOIN strains_strain_feelings ssf ON sf.id = ssf.feeling_id
                WHERE ssf.strain_id = %s
            """, (strain_id,))
            strain_data['feelings'] = [row[0] for row in cursor.fetchall()]
            
            # Fetch helps_with
            cursor.execute("""
                SELECT sh.name FROM strains_helpswith sh
                JOIN strains_strain_helps_with sshw ON sh.id = sshw.helpswith_id
                WHERE sshw.strain_id = %s
            """, (strain_id,))
            strain_data['helps_with'] = [row[0] for row in cursor.fetchall()]
            
            # Fetch negatives
            cursor.execute("""
                SELECT sn.name FROM strains_negative sn
                JOIN strains_strain_negatives ssn ON sn.id = ssn.negative_id
                WHERE ssn.strain_id = %s
            """, (strain_id,))
            strain_data['negatives'] = [row[0] for row in cursor.fetchall()]
            
            # Fetch flavors
            cursor.execute("""
                SELECT sf.name FROM strains_flavor sf
                JOIN strains_strain_flavors ssf ON sf.id = ssf.flavor_id
                WHERE ssf.strain_id = %s
            """, (strain_id,))
            strain_data['flavors'] = [row[0] for row in cursor.fetchall()]
            
            strains.append(strain_data)
        
        cursor.close()
        conn.close()
        
        print(f"📊 Fetched {len(strains)} strains from cannamente")
        return strains
        
    except Exception as e:
        print(f"❌ Error fetching strains from cannamente: {e}")
        if conn:
            conn.close()
        return []


def clear_all_strain_data():
    """Clear all existing strain data (for full re-sync)"""
    try:
        local_conn = get_local_connection()
        cursor = local_conn.cursor()
        
        # Clear in correct order due to foreign key constraints
        cursor.execute("DELETE FROM strains_strain")
        local_conn.commit()
        
        cursor.close()
        local_conn.close()
        
        print("🗑️ Cleared all existing strain data")
        return True
        
    except Exception as e:
        print(f"❌ Error clearing strain data: {e}")
        return False


def print_summary(strains_processed: int, sync_type: str, success: bool):
    """Print a summary of the synchronization operation"""
    status_icon = "🎉" if success else "❌"
    status_text = "completed successfully" if success else "failed"
    
    print("\n" + "="*60)
    print(f"{status_icon} {sync_type.upper()} synchronization {status_text}!")
    print(f"💡 Processed {strains_processed} strains")
    
    if success:
        print("🔍 The AI Budtender system is ready to serve recommendations!")
    else:
        print("⚠️ Please check the errors above and try again")
    
    print("="*60)