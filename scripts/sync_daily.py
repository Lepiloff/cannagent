#!/usr/bin/env python3
"""
Daily incremental synchronization script for AI Budtender.

This script performs incremental updates to keep the local database
synchronized with the cannamente source database:

1. Finds strains that were added/updated since last sync
2. Updates only changed strains (preserves existing data)
3. Generates embeddings only for new/updated strains
4. Handles deletions by marking strains as inactive

Designed to run as a daily cron job for efficient data synchronization.

Usage:
    python scripts/sync_daily.py
    
    # Or with custom sync window
    python scripts/sync_daily.py --since "2024-01-01"

Environment Variables:
    Same as init_database.py - uses graceful fallback if cannamente unavailable
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Set

# Add parent directory to path to import app modules  
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.common import (
    validate_environment,
    fetch_strains_from_cannamente,
    get_last_sync_time,
    record_sync_metadata,
    print_summary,
    get_local_connection
)
from app.db.database import SessionLocal
from app.db.repository import StrainRepository
from app.core.rag_service import RAGService


def get_existing_strain_mapping() -> Dict[str, Dict]:
    """Get mapping of existing strains by name for comparison"""
    session = SessionLocal()
    repo = StrainRepository(session)
    
    try:
        strains = repo.get_all_strains()
        strain_map = {}
        
        for strain in strains:
            strain_map[strain.name] = {
                'id': strain.id,
                'updated_at': strain.updated_at,
                'active': strain.active
            }
        
        session.close()
        return strain_map
        
    except Exception as e:
        print(f"❌ Error getting existing strains: {e}")
        session.close()
        return {}


def sync_incremental_strains(strains_data: List[Dict], existing_strains: Dict[str, Dict]) -> Dict[str, int]:
    """
    Perform incremental sync of strain data.
    
    Returns:
        Dictionary with counts: {'new': int, 'updated': int, 'errors': int}
    """
    if not strains_data:
        print("ℹ️ No new or updated strains found")
        return {'new': 0, 'updated': 0, 'errors': 0}
    
    print(f"🔄 Processing {len(strains_data)} changed strains...")
    
    session = SessionLocal()
    repo = StrainRepository(session)
    
    counts = {'new': 0, 'updated': 0, 'errors': 0}
    
    try:
        for i, strain_data in enumerate(strains_data, 1):
            strain_name = strain_data.get('name', 'Unknown')
            
            try:
                if strain_name in existing_strains:
                    # Update existing strain
                    existing_id = existing_strains[strain_name]['id']
                    strain = repo.update_strain_with_relations(existing_id, strain_data)
                    counts['updated'] += 1
                    operation = "updated"
                else:
                    # Create new strain
                    strain = repo.create_strain_with_relations(strain_data)
                    counts['new'] += 1
                    operation = "created"
                
                # Progress indicator
                if i % 10 == 0:
                    print(f"  🔄 Processed {i} strains...")
                    
            except Exception as e:
                counts['errors'] += 1
                print(f"❌ Error {operation if 'operation' in locals() else 'processing'} strain '{strain_name}': {e}")
                
                if counts['errors'] > 5:  # Stop if too many errors
                    print("❌ Too many errors, stopping incremental sync")
                    break
                continue
        
        session.commit()
        
        total_processed = counts['new'] + counts['updated']
        print(f"✅ Incremental sync completed: {counts['new']} new, {counts['updated']} updated, {counts['errors']} errors")
        
        return counts
        
    except Exception as e:
        session.rollback()
        print(f"❌ Critical error during incremental sync: {e}")
        counts['errors'] = len(strains_data)  # Mark all as failed
        return counts
        
    finally:
        session.close()


def mark_deleted_strains(cannamente_strain_names: Set[str], existing_strains: Dict[str, Dict]) -> int:
    """
    Mark strains as inactive if they no longer exist in cannamente.
    
    Args:
        cannamente_strain_names: Set of strain names currently in cannamente  
        existing_strains: Dict of existing local strains
        
    Returns:
        Number of strains marked as inactive
    """
    session = SessionLocal()
    repo = StrainRepository(session)
    
    deactivated_count = 0
    
    try:
        for strain_name, strain_info in existing_strains.items():
            # If strain exists locally but not in cannamente, mark as inactive
            if strain_info['active'] and strain_name not in cannamente_strain_names:
                try:
                    repo.deactivate_strain(strain_info['id'])
                    deactivated_count += 1
                    print(f"🔄 Deactivated strain: {strain_name}")
                except Exception as e:
                    print(f"❌ Error deactivating strain '{strain_name}': {e}")
        
        session.commit()
        
        if deactivated_count > 0:
            print(f"✅ Deactivated {deactivated_count} strains no longer in source")
        
        return deactivated_count
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error marking deleted strains: {e}")
        return 0
        
    finally:
        session.close()


def generate_embeddings_for_updated_strains(strain_names: List[str]) -> bool:
    """Generate embeddings only for newly created or updated strains"""
    if not strain_names:
        print("ℹ️ No strains need new embeddings")
        return True
    
    print(f"🔗 Generating embeddings for {len(strain_names)} updated strains...")
    
    try:
        rag_service = RAGService()
        session = SessionLocal() 
        repo = StrainRepository(session)
        
        success_count = 0
        error_count = 0
        
        for i, strain_name in enumerate(strain_names, 1):
            try:
                # Get strain by name
                strain = repo.get_strain_by_name(strain_name)
                if not strain:
                    print(f"⚠️ Strain not found: {strain_name}")
                    continue
                
                # Generate and update embedding
                embedding = rag_service.generate_embedding(strain)
                if embedding:
                    repo.update_strain_embedding(strain.id, embedding)
                    success_count += 1
                else:
                    error_count += 1
                
                # Progress indicator
                if i % 5 == 0:
                    print(f"  🔗 Generated embeddings for {i} strains...")
                    
            except Exception as e:
                error_count += 1
                print(f"❌ Error generating embedding for '{strain_name}': {e}")
                continue
        
        session.commit()
        session.close()
        
        print(f"✅ Embedding generation completed: {success_count} success, {error_count} errors")
        return error_count == 0
        
    except Exception as e:
        print(f"❌ Critical error during embedding generation: {e}")
        return False


def main():
    """Main daily synchronization process"""
    parser = argparse.ArgumentParser(description='Daily incremental strain synchronization')
    parser.add_argument('--since', help='Sync strains modified since this date (YYYY-MM-DD)')
    parser.add_argument('--force-full', action='store_true', help='Force full sync instead of incremental')
    
    args = parser.parse_args()
    
    print("🚀 Starting DAILY strain synchronization...")
    start_time = datetime.now()
    
    try:
        # Step 1: Validate environment (with graceful failure for missing vars)
        print("\n" + "="*50)
        print("STEP 1: Environment Check")
        print("="*50)
        try:
            validate_environment()
        except ValueError as e:
            print(f"⚠️ Environment validation warning: {e}")
            print("ℹ️ Continuing with available configuration...")
        
        # Step 2: Determine sync window
        print("\n" + "="*50)
        print("STEP 2: Determine Sync Window")
        print("="*50)
        
        if args.since:
            sync_since = datetime.strptime(args.since, '%Y-%m-%d')
            print(f"📅 Using custom sync date: {sync_since}")
        elif args.force_full:
            sync_since = None
            print("📅 Forcing full synchronization")
        else:
            sync_since = get_last_sync_time()
            if sync_since:
                print(f"📅 Last sync: {sync_since}")
            else:
                print("📅 No previous sync found - performing full sync")
        
        # Step 3: Get existing strains for comparison
        print("\n" + "="*50)
        print("STEP 3: Analyze Current Data")
        print("="*50)
        existing_strains = get_existing_strain_mapping()
        print(f"📊 Found {len(existing_strains)} existing strains in local database")
        
        # Step 4: Fetch changed strains from cannamente
        print("\n" + "="*50)
        print("STEP 4: Fetch Source Changes")
        print("="*50)
        changed_strains = fetch_strains_from_cannamente(since=sync_since)
        
        if not changed_strains:
            print("ℹ️ No changes found in source database")
            record_sync_metadata('incremental', 0, success=True)
            print_summary(0, 'DAILY SYNC', True)
            return True
        
        # Step 5: Perform incremental sync
        print("\n" + "="*50)
        print("STEP 5: Apply Changes")
        print("="*50)
        sync_counts = sync_incremental_strains(changed_strains, existing_strains)
        
        total_synced = sync_counts['new'] + sync_counts['updated']
        
        if sync_counts['errors'] > 0 and total_synced == 0:
            raise Exception("All strain synchronization attempts failed")
        
        # Step 6: Handle deletions (mark as inactive)
        print("\n" + "="*50)
        print("STEP 6: Handle Deletions")
        print("="*50)
        
        # Get all current strain names from cannamente (for deletion detection)
        all_current_strains = fetch_strains_from_cannamente()
        current_strain_names = {s['name'] for s in all_current_strains} if all_current_strains else set()
        
        if current_strain_names:
            deactivated_count = mark_deleted_strains(current_strain_names, existing_strains)
            if deactivated_count > 0:
                total_synced += deactivated_count
        
        # Step 7: Generate embeddings for changed strains
        if total_synced > 0:
            print("\n" + "="*50)
            print("STEP 7: Update Vector Embeddings")
            print("="*50)
            
            # Get names of strains that need new embeddings
            updated_strain_names = [s['name'] for s in changed_strains]
            generate_embeddings_for_updated_strains(updated_strain_names)
        
        # Step 8: Record success
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        sync_type = 'full' if not sync_since else 'incremental'
        record_sync_metadata(sync_type, total_synced, success=True)
        
        print_summary(total_synced, 'DAILY SYNC', True)
        print(f"⏱️ Sync completed in {duration:.1f} seconds")
        print(f"📈 New: {sync_counts['new']}, Updated: {sync_counts['updated']}")
        
        return True
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        record_sync_metadata('incremental', 0, success=False)
        print(f"❌ Daily sync failed after {duration:.1f} seconds: {e}")
        print_summary(0, 'DAILY SYNC', False)
        
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)