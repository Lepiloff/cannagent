#!/usr/bin/env python3
"""
Script to check connection to external cannamente database
"""

import psycopg2
import os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def check_db_connection():
    """Check connection to external database"""
    
    # Database connection parameters
    db_params = {
        'host': 'localhost',
        'port': 5432,
        'database': 'mydatabase',
        'user': 'myuser',
        'password': 'mypassword'
    }
    
    try:
        print("🔍 Checking connection to external cannamente database...")
        
        # Connect to database
        conn = psycopg2.connect(**db_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Create cursor
        cursor = conn.cursor()
        
        # Check database info
        cursor.execute("SELECT current_database(), current_user, version()")
        db_info = cursor.fetchone()
        
        print(f"✅ Connected successfully!")
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
            print("   Run: make init-pgvector")
        
        # Check strains_strain table (Django table from cannamente)
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
                print("❌ strains_strain table missing embedding column")
                print("   Run: make init-pgvector")
            
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
        
        # Check legacy products table
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'products'
            )
        """)
        products_table_exists = cursor.fetchone()[0]
        
        if products_table_exists:
            print("✅ products table exists (legacy)")
            
            # Count products
            cursor.execute("SELECT COUNT(*) FROM products")
            count = cursor.fetchone()[0]
            print(f"   Products count: {count}")
        else:
            print("ℹ️  products table does not exist (will be created if needed)")
        
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        print("\nPossible solutions:")
        print("1. Make sure cannamente project is running")
        print("2. Check if PostgreSQL is accessible on localhost:5432")
        print("3. Verify database credentials")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    success = check_db_connection()
    if success:
        print("\n✅ Database connection check completed successfully!")
    else:
        print("\n❌ Database connection check failed!")
        exit(1) 