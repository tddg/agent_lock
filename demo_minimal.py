#!/usr/bin/env python3

"""
Minimal Demo: Drop-in transaction support for existing agents.

Shows the core concept with minimal output.
"""

import os
import sqlite3
from tx_auto_simple import transactional


# BEFORE: Original agent code
def original_blog_function(slug: str, title: str):
    """Original code - no transaction safety."""
    # File operation
    with open(f"{slug}.md", "w") as f:
        f.write(f"# {title}\n\nContent here...")
    
    # Database operation  
    conn = sqlite3.connect("blog.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS posts (slug TEXT, title TEXT)")
    cursor.execute("INSERT INTO posts (slug, title) VALUES (?, ?)", (slug, title))
    conn.commit()
    conn.close()


# AFTER: Same code + @transactional (1 line change!)
@transactional  # <-- ONLY CHANGE NEEDED
def transactional_blog_function(slug: str, title: str):
    """Same code with transaction safety."""
    # EXACT SAME CODE - zero changes!
    with open(f"{slug}.md", "w") as f:
        f.write(f"# {title}\n\nContent here...")
    
    conn = sqlite3.connect("blog.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS posts (slug TEXT, title TEXT)")
    cursor.execute("INSERT INTO posts (slug, title) VALUES (?, ?)", (slug, title))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    print("Testing original function...")
    original_blog_function("test1", "Test Post 1")
    print("✓ Original completed")
    
    print("\nTesting transactional function...")
    transactional_blog_function("test2", "Test Post 2") 
    print("✓ Transactional completed")
    
    print("\n" + "="*50)
    print("MIGRATION SUMMARY")
    print("="*50)
    print("Code changes needed: 1 line (@transactional)")
    print("Existing code changes: 0 lines")
    print("Transaction benefits: ✓ Atomic ✓ Rollback ✓ Logging")
    print("="*50)
    
    # Cleanup
    for f in ["test1.md", "test2.md", "blog.db"]:
        if os.path.exists(f):
            os.remove(f)