#!/usr/bin/env python3
"""
Database initialization script for AI Budtender production deployment.

This script performs complete database setup from scratch:
1. Validates environment variables
2. Installs pgvector extension  
3. Creates all database tables
4. Syncs all strains from cannamente
5. Generates embeddings for vector search

Usage:
    python scripts/init_database.py

Environment Variables (Required for production):
    CANNAMENTE_POSTGRES_HOST - Cannamente database host
    CANNAMENTE_POSTGRES_DB - Cannamente database name  
    CANNAMENTE_POSTGRES_USER - Cannamente database user
    CANNAMENTE_POSTGRES_PASSWORD - Cannamente database password
    ENVIRONMENT - Set to 'production' for prod deployment
"""

import os
import sys
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.common import (
    validate_environment,
    ensure_pgvector_extension, 
    create_database_schema,
    fetch_strains_from_cannamente,
    clear_all_strain_data,
    record_sync_metadata,
    print_summary,
    get_local_connection
)
from app.db.database import SessionLocal
from app.db.repository import StrainRepository
from app.core.rag_service import RAGService


def sync_strains_to_local_db(strains_data):
    """Sync strain data to local database with relations"""
    if not strains_data:
        print("⚠️ No strain data to sync")
        return 0
    
    print(f"🔄 Syncing {len(strains_data)} strains to local database...")
    
    session = SessionLocal()
    repo = StrainRepository(session)
    synced_count = 0
    error_count = 0
    
    try:
        for i, strain_data in enumerate(strains_data, 1):
            try:
                # Create strain record
                strain = repo.create_strain_with_relations(strain_data)
                synced_count += 1
                
                # Progress indicator
                if i % 20 == 0:
                    print(f"  📦 Synced {i} strains...")
                    
            except Exception as e:
                error_count += 1
                print(f"❌ Error syncing strain '{strain_data.get('name', 'Unknown')}': {e}")
                if error_count > 10:  # Stop if too many errors
                    print("❌ Too many errors, stopping sync")
                    break
                continue
        
        session.commit()
        print(f"✅ Strain sync completed: {synced_count} success, {error_count} errors")
        return synced_count
        
    except Exception as e:
        session.rollback()
        print(f"❌ Critical error during strain sync: {e}")
        return 0
        
    finally:
        session.close()


def generate_embeddings():
    """Generate embeddings for all synced strains"""
    print("🔄 Generating embeddings for vector search...")
    
    try:
        rag_service = RAGService()
        session = SessionLocal()
        repo = StrainRepository(session)
        
        # Get all strains without embeddings
        strains = repo.get_strains_without_embeddings()
        
        if not strains:
            print("✅ All strains already have embeddings")
            session.close()
            return True
        
        print(f"🔗 Generating embeddings for {len(strains)} strains...")
        
        success_count = 0
        error_count = 0
        
        for i, strain in enumerate(strains, 1):
            try:
                # Generate embedding
                embedding = rag_service.generate_embedding(strain)
                if embedding:
                    # Update strain with embedding
                    repo.update_strain_embedding(strain.id, embedding)
                    success_count += 1
                else:
                    error_count += 1
                
                # Progress indicator  
                if i % 10 == 0:
                    print(f"  🔗 Generated embeddings for {i} strains...")
                    
            except Exception as e:
                error_count += 1
                print(f"❌ Error generating embedding for strain '{strain.name}': {e}")
                if error_count > 10:  # Stop if too many errors
                    print("❌ Too many errors, stopping embedding generation")
                    break
                continue
        
        session.commit()
        session.close()
        
        print(f"✅ Embedding generation completed: {success_count} success, {error_count} errors")
        return error_count == 0
        
    except Exception as e:
        print(f"❌ Critical error during embedding generation: {e}")
        return False


def main():
    """Main initialization process for production deployment"""
    print("🚀 Starting COMPLETE database initialization for AI Budtender...")
    print("📋 This will set up the database from scratch for production deployment")
    
    start_time = datetime.now()
    
    try:
        # Step 1: Validate environment
        print("\n" + "="*50)
        print("STEP 1: Environment Validation")
        print("="*50)
        validate_environment()
        
        # Step 2: Ensure pgvector extension
        print("\n" + "="*50) 
        print("STEP 2: Database Extensions")
        print("="*50)
        if not ensure_pgvector_extension():
            raise Exception("Failed to install pgvector extension")
        
        # Step 3: Create database schema
        print("\n" + "="*50)
        print("STEP 3: Database Schema")  
        print("="*50)
        if not create_database_schema():
            raise Exception("Failed to create database schema")
        
        # Step 4: Clear existing data (full re-init)
        print("\n" + "="*50)
        print("STEP 4: Clear Existing Data")
        print("="*50)
        if not clear_all_strain_data():
            raise Exception("Failed to clear existing data")
        
        # Step 5: Fetch strains from cannamente
        print("\n" + "="*50)
        print("STEP 5: Fetch Source Data")
        print("="*50)
        strains = fetch_strains_from_cannamente()
        
        if not strains:
            print("⚠️ No strains found - continuing with empty database")
            strains_synced = 0
        else:
            # Step 6: Sync strains to local database
            print("\n" + "="*50)
            print("STEP 6: Sync Strain Data")
            print("="*50)
            strains_synced = sync_strains_to_local_db(strains)
            
            if strains_synced == 0:
                raise Exception("Failed to sync any strains")
            
            # Step 7: Generate embeddings
            print("\n" + "="*50)
            print("STEP 7: Generate Vector Embeddings")
            print("="*50)
            if not generate_embeddings():
                print("⚠️ Some embeddings failed - vector search may be limited")
        
        # Step 8: Record success
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        record_sync_metadata('full_init', strains_synced, success=True)
        
        print_summary(strains_synced, 'FULL INITIALIZATION', True)
        print(f"⏱️ Total initialization time: {duration:.1f} seconds")
        
        return True
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        record_sync_metadata('full_init', 0, success=False)
        print(f"❌ Initialization failed after {duration:.1f} seconds: {e}")
        print_summary(0, 'FULL INITIALIZATION', False)
        
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)