#!/usr/bin/env python3
"""
Database migration script to add model usage tracking fields.
Run this script to update the database schema.

Usage:
    python run_migration.py
"""

import sqlite3
import sys
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent / "vizhi.db"

def run_migration():
    """Add new columns to model_connections table."""
    
    if not DB_PATH.exists():
        print(f"❌ Database not found at: {DB_PATH}")
        print("   Please check the database path.")
        sys.exit(1)
    
    print(f"📁 Found database at: {DB_PATH}")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("\n🔄 Running migration...")
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(model_connections)")
        columns = {col[1] for col in cursor.fetchall()}
        
        migrations_run = []
        
        # Add last_used_at column
        if "last_used_at" not in columns:
            print("   ➕ Adding column: last_used_at")
            cursor.execute("""
                ALTER TABLE model_connections 
                ADD COLUMN last_used_at TIMESTAMP
            """)
            migrations_run.append("last_used_at")
        else:
            print("   ✓ Column already exists: last_used_at")
        
        # Add total_tokens_consumed column
        if "total_tokens_consumed" not in columns:
            print("   ➕ Adding column: total_tokens_consumed")
            cursor.execute("""
                ALTER TABLE model_connections 
                ADD COLUMN total_tokens_consumed INTEGER DEFAULT 0
            """)
            migrations_run.append("total_tokens_consumed")
        else:
            print("   ✓ Column already exists: total_tokens_consumed")
        
        # Add total_cost column
        if "total_cost" not in columns:
            print("   ➕ Adding column: total_cost")
            cursor.execute("""
                ALTER TABLE model_connections 
                ADD COLUMN total_cost REAL DEFAULT 0.0
            """)
            migrations_run.append("total_cost")
        else:
            print("   ✓ Column already exists: total_cost")
        
        # Update existing rows to have default values
        if migrations_run:
            print("\n   🔧 Updating existing rows with default values...")
            cursor.execute("""
                UPDATE model_connections 
                SET 
                    total_tokens_consumed = COALESCE(total_tokens_consumed, 0),
                    total_cost = COALESCE(total_cost, 0.0)
            """)
            affected = cursor.rowcount
            print(f"   ✓ Updated {affected} existing row(s)")
        
        conn.commit()
        
        if migrations_run:
            print(f"\n✅ Migration completed successfully!")
            print(f"   Added columns: {', '.join(migrations_run)}")
        else:
            print("\n✅ Database schema is already up to date!")
        
        print("\n📊 Current model_connections schema:")
        cursor.execute("PRAGMA table_info(model_connections)")
        for col in cursor.fetchall():
            print(f"   - {col[1]} ({col[2]})")
        
    except sqlite3.Error as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
    
    finally:
        conn.close()
    
    print("\n✨ Done! You can now restart your backend server.")

if __name__ == "__main__":
    print("=" * 60)
    print("  Database Migration: Add Model Usage Tracking Fields")
    print("=" * 60)
    run_migration()
