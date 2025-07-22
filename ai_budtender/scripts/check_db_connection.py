#!/usr/bin/env python3
"""
Script to check connection to local database and cannamente availability
"""

import psycopg2
import os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def check_cannamente_connection():
    """Check if cannamente database is available for sync"""
    
    # Database connection parameters for cannamente
    db_params = {
        'host': 'localhost',
        'port': 5432,
        'database': 'mydatabase',
        'user': 'myuser',
        'password': 'mypassword'
    }
    
    try:
        print("🔍 Checking cannamente database availability...")
        
        # Connect to cannamente database
        conn = psycopg2.connect(**db_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Create cursor
        cursor = conn.cursor()
        
        # Check database info
        cursor.execute("SELECT current_database(), current_user, version()")
        db_info = cursor.fetchone()
        
        print(f"✅ Cannamente database is available!")
        print(f"   Database: {db_info[0]}")
        print(f"   User: {db_info[1]}")
        print(f"   PostgreSQL: {db_info[2].split(',')[0]}")
        
        # Check strains_strain table
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'strains_strain'
            )
        """)
        strains_table_exists = cursor.fetchone()[0]
        
        if strains_table_exists:
            # Try to count strains (ignore pgvector errors)
            try:
                cursor.execute("SELECT COUNT(*) FROM strains_strain WHERE active = true")
                count = cursor.fetchone()[0]
                print(f"✅ Found {count} active strains in cannamente")
                return True
            except Exception as e:
                if "vector" in str(e):
                    print("⚠️  Found strains_strain table but pgvector extension has issues")
                    print("   This is expected - we'll use local database for vector operations")
                    return True
                else:
                    print(f"❌ Error counting strains: {e}")
                    return False
        else:
            print("❌ strains_strain table does not exist in cannamente")
            return False
        
    except psycopg2.OperationalError as e:
        print(f"❌ Cannamente database is not available: {e}")
        print("   Make sure cannamente project is running:")
        print("   cd ../cannamente && docker-compose up -d")
        return False
    except Exception as e:
        print(f"❌ Error checking cannamente: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


def check_local_db_connection():
    """Check connection to local AI Budtender database"""
    
    # Database connection parameters for local DB
    db_params = {
        'host': 'localhost',
        'port': 5433,  # Local AI Budtender DB
        'database': 'ai_budtender',
        'user': 'ai_user',
        'password': 'ai_password'
    }
    
    try:
        print("🔍 Checking local AI Budtender database...")
        
        # Connect to local database
        conn = psycopg2.connect(**db_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Create cursor
        cursor = conn.cursor()
        
        # Check database info
        cursor.execute("SELECT current_database(), current_user, version()")
        db_info = cursor.fetchone()
        
        print(f"✅ Local database is available!")
        print(f"   Database: {db_info[0]}")
        print(f"   User: {db_info[1]}")
        print(f"   PostgreSQL: {db_info[2].split(',')[0]}")
        
        # Check pgvector extension
        cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
        pgvector = cursor.fetchone()
        
        if pgvector:
            print("✅ pgvector extension is installed")
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            version = cursor.fetchone()
            if version:
                print(f"   pgvector version: {version[0]}")
        else:
            print("❌ pgvector extension is NOT installed")
            print("   This should not happen with local database")
            return False
        
        # Check strains table
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'strains'
            )
        """)
        strains_table_exists = cursor.fetchone()[0]
        
        if strains_table_exists:
            # Count strains
            cursor.execute("SELECT COUNT(*) FROM strains")
            count = cursor.fetchone()[0]
            print(f"✅ Found {count} strains in local database")
            
            # Check if strains have embeddings
            cursor.execute("SELECT COUNT(*) FROM strains WHERE embedding IS NOT NULL")
            with_embeddings = cursor.fetchone()[0]
            print(f"   Strains with embeddings: {with_embeddings}")
            
            # Show sample strains
            if count > 0:
                cursor.execute("SELECT title, category, thc, cbd FROM strains LIMIT 3")
                sample_strains = cursor.fetchall()
                print("   Sample strains:")
                for strain in sample_strains:
                    print(f"     - {strain[0]} ({strain[1]}) - THC: {strain[2]}%, CBD: {strain[3]}%")
        else:
            print("❌ strains table does not exist in local database")
            print("   Run: make sync-cannamente to initialize data")
            return False
        
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Local database is not available: {e}")
        print("   Make sure AI Budtender is running:")
        print("   make start")
        return False
    except Exception as e:
        print(f"❌ Error checking local database: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


def main():
    """Main check function"""
    print("🔧 AI Budtender Database Health Check")
    print("=" * 50)
    
    # Check cannamente availability
    cannamente_ok = check_cannamente_connection()
    print()
    
    # Check local database
    local_ok = check_local_db_connection()
    print()
    
    # Summary
    print("📊 Summary:")
    if cannamente_ok and local_ok:
        print("✅ All systems operational!")
        print("   - Cannamente database is available for sync")
        print("   - Local database is working with pgvector")
        print("   - AI Budtender is ready to use")
        return True
    elif local_ok and not cannamente_ok:
        print("⚠️  Local database is working, but cannamente is not available")
        print("   - AI Budtender will work with existing data")
        print("   - Run 'make sync-cannamente' when cannamente is available")
        return True
    elif not local_ok:
        print("❌ Local database is not working")
        print("   - Run 'make start' to start AI Budtender")
        return False
    else:
        print("❌ No databases are available")
        print("   - Start cannamente: cd ../cannamente && docker-compose up -d")
        print("   - Start AI Budtender: make start")
        return False


if __name__ == "__main__":
    success = main()
    if not success:
        exit(1) 