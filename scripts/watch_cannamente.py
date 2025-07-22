#!/usr/bin/env python3
"""
Script to watch for new strains in cannamente and sync them to AI Budtender
This simulates real-time sync with client databases in production
"""

import psycopg2
import time
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


def get_last_sync_time() -> datetime:
    """Get the last sync time from local database"""
    conn = get_local_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT MAX(updated_at) FROM strains 
            WHERE updated_at IS NOT NULL
        """)
        result = cursor.fetchone()
        return result[0] if result[0] else datetime.min
    finally:
        cursor.close()
        conn.close()


def get_new_strains_from_cannamente(since: datetime) -> List[Dict[str, Any]]:
    """Get new strains from cannamente since last sync"""
    conn = get_cannamente_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT 
                id, title, text_content, cbd, thc, cbg, 
                rating, category, img, img_alt_text, 
                active, top, main, is_review, slug
            FROM strains_strain 
            WHERE active = true 
            AND (updated_at > %s OR created_at > %s)
        """, (since, since))
        
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
        
        return strains
        
    finally:
        cursor.close()
        conn.close()


def sync_strain_to_local_db(strain: Dict[str, Any]):
    """Sync a single strain to local database"""
    conn = get_local_connection()
    cursor = conn.cursor()
    
    try:
        # Upsert strain data
        cursor.execute("""
            INSERT INTO strains (
                id, title, text_content, cbd, thc, cbg,
                rating, category, img, img_alt_text,
                active, top, main, is_review, slug,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                text_content = EXCLUDED.text_content,
                cbd = EXCLUDED.cbd,
                thc = EXCLUDED.thc,
                cbg = EXCLUDED.cbg,
                rating = EXCLUDED.rating,
                category = EXCLUDED.category,
                img = EXCLUDED.img,
                img_alt_text = EXCLUDED.img_alt_text,
                active = EXCLUDED.active,
                top = EXCLUDED.top,
                main = EXCLUDED.main,
                is_review = EXCLUDED.is_review,
                slug = EXCLUDED.slug,
                updated_at = EXCLUDED.updated_at
        """, (
            strain['id'], strain['title'], strain['text_content'],
            strain['cbd'], strain['thc'], strain['cbg'],
            strain['rating'], strain['category'], strain['img'],
            strain['img_alt_text'], strain['active'], strain['top'],
            strain['main'], strain['is_review'], strain['slug'],
            datetime.now(), datetime.now()
        ))
        
        conn.commit()
        print(f"✅ Synced strain: {strain['title']} (ID: {strain['id']})")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error syncing strain {strain['title']}: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def watch_and_sync(interval: int = 30):
    """Watch for new strains and sync them automatically"""
    print(f"🔍 Starting watch mode - checking every {interval} seconds...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            try:
                # Get last sync time
                last_sync = get_last_sync_time()
                
                # Get new strains
                new_strains = get_new_strains_from_cannamente(last_sync)
                
                if new_strains:
                    print(f"🔄 Found {len(new_strains)} new strains, syncing...")
                    
                    for strain in new_strains:
                        sync_strain_to_local_db(strain)
                    
                    print(f"✅ Synced {len(new_strains)} strains at {datetime.now()}")
                else:
                    print(f"⏰ No new strains found at {datetime.now()}")
                
                # Wait before next check
                time.sleep(interval)
                
            except KeyboardInterrupt:
                print("\n🛑 Watch mode stopped by user")
                break
            except Exception as e:
                print(f"❌ Error in watch mode: {e}")
                print("Retrying in 60 seconds...")
                time.sleep(60)
                
    except KeyboardInterrupt:
        print("\n🛑 Watch mode stopped")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Watch and sync strains from cannamente')
    parser.add_argument('--interval', type=int, default=30, 
                       help='Check interval in seconds (default: 30)')
    parser.add_argument('--once', action='store_true',
                       help='Sync once and exit')
    
    args = parser.parse_args()
    
    if args.once:
        print("🔄 One-time sync...")
        last_sync = get_last_sync_time()
        new_strains = get_new_strains_from_cannamente(last_sync)
        
        if new_strains:
            print(f"📊 Found {len(new_strains)} new strains")
            for strain in new_strains:
                sync_strain_to_local_db(strain)
            print("✅ One-time sync completed")
        else:
            print("ℹ️  No new strains found")
    else:
        watch_and_sync(args.interval)


if __name__ == "__main__":
    main() 