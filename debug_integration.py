#!/usr/bin/env python3

import asyncio
import tempfile
import sqlite3
from pathlib import Path
import shutil

from tx_mini import Transaction, Op
from adaptors import FileSystemAdaptor, SQLiteAdaptor


async def test_integration():
    """Debug integration test."""
    temp_dir = tempfile.mkdtemp()
    db_file = tempfile.mktemp(suffix='.db')
    
    try:
        print(f"Using temp dir: {temp_dir}")
        print(f"Using db file: {db_file}")
        
        # Setup database
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY,
                slug TEXT UNIQUE,
                title TEXT,
                content TEXT
            )
        """)
        conn.commit()
        conn.close()
        
        fs_adaptor = FileSystemAdaptor(temp_dir)
        db_adaptor = SQLiteAdaptor(db_file)
        
        print("Starting transaction...")
        async with Transaction("create_blog_post") as tx:
            print("Creating operations...")
            file_op = Op("fs.write", {"path": "posts/hello-world.md", "data": "# Hello World\n\nThis is my first post!"})
            db_op = Op("db.exec", {
                "sql": "INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
                "params": ("hello-world", "Hello World", "This is my first post!")
            })
            
            print(f"Registering file operation: {file_op.op_id}")
            tx.register(file_op, fs_adaptor)
            
            print(f"Registering db operation: {db_op.op_id}")
            tx.register(db_op, db_adaptor)
            
            print(f"Transaction has {len(tx.ops)} operations")
        
        print(f"Transaction state: {tx.state}")
        print("Transaction completed, checking results...")
        
        # Check what happened to temp files
        print(f"FS adaptor temp files: {fs_adaptor.temp_files}")
        print(f"DB adaptor connections: {db_adaptor.connections}")
        
        # Verify file was created
        file_path = Path(temp_dir) / "posts" / "hello-world.md"
        print(f"File exists: {file_path.exists()}")
        if file_path.exists():
            print(f"File content: {file_path.read_text()}")
        
        # Verify database record was created
        conn = sqlite3.connect(db_file)
        cursor = conn.execute("SELECT title FROM posts WHERE slug = ?", ("hello-world",))
        result = cursor.fetchone()
        conn.close()
        print(f"DB result: {result}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        import os
        if os.path.exists(db_file):
            os.unlink(db_file)


if __name__ == "__main__":
    asyncio.run(test_integration())