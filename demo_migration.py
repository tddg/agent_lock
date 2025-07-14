#!/usr/bin/env python3

"""
Demo: Migrating existing single-file-agents to use transactions with minimal changes.

Shows before/after comparison and tests the automatic transaction detection.
"""

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

from tx_auto import transactional, auto_transaction


# ============================================================================
# BEFORE: Original agent function (no transaction safety)
# ============================================================================

def create_blog_post_original(slug: str, title: str, content: str):
    """Original function - no transaction safety."""
    print(f"[ORIGINAL] Creating blog post: {slug}")
    
    # File operation
    os.makedirs("blog_posts", exist_ok=True)
    with open(f"blog_posts/{slug}.md", "w") as f:
        f.write(f"# {title}\n\n{content}")
    
    # Database operation
    conn = sqlite3.connect("blog.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            slug TEXT PRIMARY KEY,
            title TEXT,
            content TEXT
        )
    """)
    cursor.execute("INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
                   (slug, title, content))
    conn.commit()
    conn.close()
    
    print(f"[ORIGINAL] Blog post created: {slug}")


# ============================================================================
# AFTER: Same function with transaction safety (1 line change!)
# ============================================================================

@transactional  # <-- ONLY CHANGE NEEDED!
def create_blog_post_transactional(slug: str, title: str, content: str):
    """Same function with transaction safety - ONLY @transactional added!"""
    print(f"[TRANSACTIONAL] Creating blog post: {slug}")
    
    # EXACT SAME CODE - no changes needed!
    os.makedirs("blog_posts", exist_ok=True)
    with open(f"blog_posts/{slug}.md", "w") as f:
        f.write(f"# {title}\n\n{content}")
    
    # EXACT SAME CODE - no changes needed!
    conn = sqlite3.connect("blog.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            slug TEXT PRIMARY KEY,
            title TEXT,
            content TEXT
        )
    """)
    cursor.execute("INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
                   (slug, title, content))
    conn.commit()
    conn.close()
    
    print(f"[TRANSACTIONAL] Blog post created: {slug}")


# ============================================================================
# Demo: File processing agent migration
# ============================================================================

@transactional  # <-- ONLY CHANGE NEEDED!
def process_data_files(input_dir: str, output_dir: str):
    """Example data processing agent with transaction safety."""
    print(f"[TRANSACTIONAL] Processing files from {input_dir} to {output_dir}")
    
    # EXISTING CODE UNCHANGED!
    os.makedirs(output_dir, exist_ok=True)
    
    # Process multiple files atomically
    for i in range(3):
        input_file = f"{input_dir}/data_{i}.txt"
        output_file = f"{output_dir}/processed_{i}.txt"
        
        # Read and transform (existing code)
        if os.path.exists(input_file):
            with open(input_file, "r") as f:
                data = f.read()
            
            # Transform data (existing code)
            processed_data = data.upper() + f"\n\nProcessed at: {asyncio.get_event_loop().time()}"
            
            # Write result (existing code)
            with open(output_file, "w") as f:
                f.write(processed_data)
        
        # Log to database (existing code)
        conn = sqlite3.connect("processing.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_log (
                input_file TEXT,
                output_file TEXT,
                status TEXT
            )
        """)
        cursor.execute("INSERT INTO processing_log VALUES (?, ?, ?)",
                       (input_file, output_file, "completed"))
        conn.commit()
        conn.close()
    
    print(f"[TRANSACTIONAL] All files processed atomically!")


# ============================================================================
# Demo: Context manager approach for ad-hoc blocks
# ============================================================================

def analyze_data_with_context():
    """Demo using context manager for transactional blocks."""
    print("[CONTEXT] Starting data analysis...")
    
    with auto_transaction():
        # EXISTING CODE UNCHANGED!
        
        # Create analysis results
        results = {"total_records": 1000, "avg_score": 85.5}
        
        with open("analysis_results.json", "w") as f:
            import json
            json.dump(results, f)
        
        # Log analysis to database
        conn = sqlite3.connect("analytics.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                timestamp TEXT,
                total_records INTEGER,
                avg_score REAL
            )
        """)
        cursor.execute("INSERT INTO analysis_runs VALUES (?, ?, ?)",
                       ("2024-01-01", results["total_records"], results["avg_score"]))
        conn.commit()
        conn.close()
    
    print("[CONTEXT] Analysis completed atomically!")


# ============================================================================
# Test failure scenarios
# ============================================================================

@transactional
def create_blog_post_with_failure(slug: str, title: str, content: str):
    """Test rollback behavior when operations fail."""
    print(f"[FAILURE TEST] Creating blog post: {slug}")
    
    # This will succeed
    os.makedirs("blog_posts", exist_ok=True)
    with open(f"blog_posts/{slug}.md", "w") as f:
        f.write(f"# {title}\n\n{content}")
    
    # This will fail (duplicate slug)
    conn = sqlite3.connect("blog.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            slug TEXT PRIMARY KEY,
            title TEXT,
            content TEXT
        )
    """)
    cursor.execute("INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
                   (slug, title, content))  # Will fail if slug exists
    conn.commit()
    conn.close()


# ============================================================================
# Migration comparison demo
# ============================================================================

async def demo_migration():
    """Demonstrate the migration approach."""
    print("=" * 60)
    print("TRANSACTION MIGRATION DEMO")
    print("=" * 60)
    
    # Clean up from previous runs
    cleanup_files()
    
    print("\n1. ORIGINAL APPROACH (No Transaction Safety)")
    print("-" * 50)
    create_blog_post_original("hello-world", "Hello World", "This is my first post!")
    
    print("\n2. TRANSACTIONAL APPROACH (Same Code + @transactional)")
    print("-" * 50)
    create_blog_post_transactional("python-guide", "Python Guide", "Learn Python step by step!")
    
    print("\n3. MULTI-FILE PROCESSING (Atomic)")
    print("-" * 50)
    setup_test_files()
    process_data_files("test_input", "test_output")
    
    print("\n4. CONTEXT MANAGER APPROACH")
    print("-" * 50)
    analyze_data_with_context()
    
    print("\n5. FAILURE HANDLING (Rollback Demo)")
    print("-" * 50)
    try:
        # This should succeed
        create_blog_post_transactional("unique-post", "Unique Post", "This will work!")
        
        # This should fail and rollback
        create_blog_post_with_failure("unique-post", "Duplicate Post", "This will fail!")
    except Exception as e:
        print(f"[EXPECTED FAILURE] Transaction rolled back: {e}")
        
        # Verify file was NOT created due to rollback
        if not Path("blog_posts/unique-post.md").exists():
            print("[SUCCESS] File rollback worked - no orphaned file!")
        else:
            print("[ERROR] File was not rolled back!")
    
    print("\n6. VERIFY TRANSACTION LOGS")
    print("-" * 50)
    tx_log_dir = Path.home() / "tx_log"
    if tx_log_dir.exists():
        log_files = list(tx_log_dir.glob("*.jsonl"))
        print(f"Transaction logs created: {len(log_files)} files")
        if log_files:
            print(f"Latest log: {log_files[-1].name}")
    
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print("Code Changes Required:")
    print("  1. Add import: from tx_auto import transactional")
    print("  2. Add decorator: @transactional")
    print("  3. Total lines changed: 2 per agent")
    print("")
    print("Benefits Gained:")
    print("  ✓ Atomic operations across file + database")
    print("  ✓ Automatic rollback on failures")
    print("  ✓ Crash-safe transaction logging")
    print("  ✓ Multi-function coordination")
    print("  ✓ Zero behavior changes for existing code")
    print("=" * 60)


def setup_test_files():
    """Setup test files for processing demo."""
    os.makedirs("test_input", exist_ok=True)
    for i in range(3):
        with open(f"test_input/data_{i}.txt", "w") as f:
            f.write(f"Sample data file {i}\nWith some content to process.")


def cleanup_files():
    """Clean up test files."""
    import shutil
    for dir_name in ["blog_posts", "test_input", "test_output"]:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
    
    for file_name in ["blog.db", "processing.db", "analytics.db", "analysis_results.json"]:
        if os.path.exists(file_name):
            os.remove(file_name)


if __name__ == "__main__":
    asyncio.run(demo_migration())