#!/usr/bin/env python3
"""
Script to sync data from cannamente database to AI Budtender local database
This simulates how we would sync with client databases in production
"""

import psycopg2
import os
from datetime import datetime
from typing import List, Dict, Any


def get_cannamente_connection():
    """Connect to cannamente database (client DB)"""
    return psycopg2.connect(
        host='localhost',
        port=5432,
        database='mydatabase',
        user='myuser',
        password='mypassword'
    )


def get_local_connection():
    """Connect to AI Budtender local database"""
    return psycopg2.connect(
        host='localhost',
        port=5433,  # Local AI Budtender DB
        database='ai_budtender',
        user='ai_user',
        password='ai_password'
    )


def fetch_strains_from_cannamente() -> List[Dict[str, Any]]:
    """Fetch strains data from cannamente (client database)"""
    conn = get_cannamente_connection()
    cursor = conn.cursor()
    
    try:
        # Read data from client's strains table
        cursor.execute("""
            SELECT 
                id, title, text_content, cbd, thc, cbg, 
                rating, category, img, img_alt_text, 
                active, top, main, is_review, slug
            FROM strains_strain 
            WHERE active = true
        """)
        
        strains = []
        for row in cursor.fetchall():
            strains.append({
                'id': row[0],
                'title': row[1],
                'text_content': row[2],
                'cbd': row[3],
                'thc': row[4],
                'cbg': row[5],
                'rating': row[6],
                'category': row[7],
                'img': row[8],
                'img_alt_text': row[9],
                'active': row[10],
                'top': row[11],
                'main': row[12],
                'is_review': row[13],
                'slug': row[14]
            })
        
        print(f"📊 Fetched {len(strains)} strains from cannamente")
        return strains
        
    finally:
        cursor.close()
        conn.close()


def sync_to_local_db(strains: List[Dict[str, Any]]):
    """Sync strains data to local AI Budtender database"""
    conn = get_local_connection()
    cursor = conn.cursor()
    
    try:
        # Clear existing data (optional - you might want incremental sync)
        cursor.execute("DELETE FROM strains")
        print("🗑️  Cleared existing strains data")
        
        # Insert strains data
        for strain in strains:
            cursor.execute("""
                INSERT INTO strains (
                    id, title, text_content, cbd, thc, cbg,
                    rating, category, img, img_alt_text,
                    active, top, main, is_review, slug,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                strain['id'], strain['title'], strain['text_content'],
                strain['cbd'], strain['thc'], strain['cbg'],
                strain['rating'], strain['category'], strain['img'],
                strain['img_alt_text'], strain['active'], strain['top'],
                strain['main'], strain['is_review'], strain['slug'],
                datetime.now(), datetime.now()
            ))
        
        conn.commit()
        print(f"✅ Synced {len(strains)} strains to local database")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error syncing data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def generate_embeddings_for_strains():
    """Generate embeddings for strains (this would be done by AI service)"""
    # This is a placeholder - in real implementation, this would:
    # 1. Fetch strains without embeddings
    # 2. Generate embeddings using OpenAI
    # 3. Update strains with embeddings
    
    conn = get_local_connection()
    cursor = conn.cursor()
    
    try:
        # Count strains without embeddings
        cursor.execute("SELECT COUNT(*) FROM strains WHERE embedding IS NULL")
        count = cursor.fetchone()[0]
        
        if count > 0:
            print(f"🔍 Found {count} strains without embeddings")
            print("💡 In production, this would generate embeddings using OpenAI")
            print("💡 For now, embeddings will be generated on-demand during chat")
        else:
            print("✅ All strains have embeddings")
            
    finally:
        cursor.close()
        conn.close()


def main():
    """Main sync process"""
    print("🔄 Starting sync from cannamente to AI Budtender...")
    
    try:
        # Step 1: Fetch data from client database (cannamente)
        strains = fetch_strains_from_cannamente()
        
        if not strains:
            print("⚠️  No strains found in cannamente database")
            return
        
        # Step 2: Sync to local database
        sync_to_local_db(strains)
        
        # Step 3: Check embeddings (placeholder for production)
        generate_embeddings_for_strains()
        
        print("✅ Sync completed successfully!")
        print("")
        print("📋 Next steps:")
        print("1. Start AI Budtender: make start-local")
        print("2. Test API: curl http://localhost:8001/api/v1/ping/")
        print("3. Test chat: curl -X POST http://localhost:8001/api/v1/chat/ask/")
        
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        exit(1)


if __name__ == "__main__":
    main() 