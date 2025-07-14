#!/usr/bin/env python3

"""
Test suite for Tx-Mini framework.
"""

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

from tx_mini import Transaction, Op, current_tx, in_transaction, tx_op
from adaptors import FileSystemAdaptor, SQLiteAdaptor


class TestTransaction:
    """Test core Transaction functionality."""
    
    def test_transaction_creation(self):
        """Test basic transaction creation."""
        tx = Transaction("test_tx")
        assert tx.name == "test_tx"
        assert tx.state == "ACTIVE"
        assert len(tx.ops) == 0
    
    def test_operation_registration(self):
        """Test operation registration."""
        tx = Transaction("test_tx")
        op = Op("test.operation", {"arg1": "value1"})
        adaptor = FileSystemAdaptor()
        
        tx.register(op, adaptor)
        
        assert len(tx.ops) == 1
        assert tx.ops[0] == op
        assert tx.adaptors[op.op_id] == adaptor
    
    def test_current_transaction_tracking(self):
        """Test thread-local transaction tracking."""
        assert current_tx() is None
        assert not in_transaction()
        
        async def test_context():
            async with Transaction("test") as tx:
                assert current_tx() == tx
                assert in_transaction()
            
            assert current_tx() is None
            assert not in_transaction()
        
        asyncio.run(test_context())


class TestFileSystemAdaptor:
    """Test FileSystemAdaptor functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.adaptor = FileSystemAdaptor(self.temp_dir)
    
    def teardown_method(self):
        """Cleanup test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    async def test_write_operation(self):
        """Test file write operation."""
        op = Op("fs.write", {"path": "test.txt", "data": "Hello, World!"})
        
        # Do operation (creates temp file)
        await self.adaptor.do(op)
        
        # File shouldn't exist yet (not prepared)
        target_path = Path(self.temp_dir) / "test.txt"
        assert not target_path.exists()
        
        # Prepare operation (move temp to final)
        await self.adaptor.prepare(op)
        
        # Now file should exist
        assert target_path.exists()
        assert target_path.read_text() == "Hello, World!"
    
    async def test_write_rollback(self):
        """Test file write rollback."""
        # Start fresh for this test
        self.teardown_method()
        self.setup_method()
        
        op = Op("fs.write", {"path": "test.txt", "data": "Hello, World!"})
        
        # Do operation
        await self.adaptor.do(op)
        
        # Undo operation (this should clean up temp file)
        await self.adaptor.undo(op)
        
        # File shouldn't exist (since it was never prepared)
        target_path = Path(self.temp_dir) / "test.txt"
        assert not target_path.exists(), f"File exists at {target_path} but should not"
        
        # Temp file should also be cleaned up
        assert op.op_id not in self.adaptor.temp_files
    
    async def test_write_overwrite_rollback(self):
        """Test rollback when overwriting existing file."""
        target_path = Path(self.temp_dir) / "existing.txt"
        target_path.write_text("Original content")
        
        op = Op("fs.write", {"path": "existing.txt", "data": "New content"})
        
        # Do and prepare operation
        await self.adaptor.do(op)
        await self.adaptor.prepare(op)
        
        # File should have new content
        assert target_path.read_text() == "New content"
        
        # Now undo (this should restore original)
        await self.adaptor.undo(op)
        
        # Should have original content back
        assert target_path.read_text() == "Original content"
    
    async def test_delete_operation(self):
        """Test file delete operation."""
        target_path = Path(self.temp_dir) / "to_delete.txt"
        target_path.write_text("Will be deleted")
        
        op = Op("fs.delete", {"path": "to_delete.txt"})
        
        # Do operation (backs up file)
        await self.adaptor.do(op)
        
        # File should still exist (not prepared yet)
        assert target_path.exists()
        
        # Prepare operation (actually delete)
        await self.adaptor.prepare(op)
        
        # File should be gone
        assert not target_path.exists()
    
    async def test_delete_rollback(self):
        """Test delete rollback."""
        target_path = Path(self.temp_dir) / "to_delete.txt"
        original_content = "Will be deleted but restored"
        target_path.write_text(original_content)
        
        op = Op("fs.delete", {"path": "to_delete.txt"})
        
        # Do and prepare operation
        await self.adaptor.do(op)
        await self.adaptor.prepare(op)
        
        # File should be gone
        assert not target_path.exists()
        
        # Undo operation
        await self.adaptor.undo(op)
        
        # File should be restored
        assert target_path.exists()
        assert target_path.read_text() == original_content


class TestSQLiteAdaptor:
    """Test SQLiteAdaptor functionality."""
    
    def setup_method(self):
        """Setup test database."""
        self.db_file = tempfile.mktemp(suffix='.db')
        self.adaptor = SQLiteAdaptor(self.db_file)
        
        # Create test table
        conn = sqlite3.connect(self.db_file)
        conn.execute("""
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT,
                value INTEGER
            )
        """)
        conn.execute("INSERT INTO test_table (name, value) VALUES ('initial', 100)")
        conn.commit()
        conn.close()
    
    def teardown_method(self):
        """Cleanup test database."""
        if os.path.exists(self.db_file):
            os.unlink(self.db_file)
    
    async def test_insert_operation(self):
        """Test database insert operation."""
        op = Op("db.exec", {
            "sql": "INSERT INTO test_table (name, value) VALUES (?, ?)",
            "params": ("test", 42)
        })
        
        # Do operation
        result = await self.adaptor.do(op)
        assert result == 1  # One row affected
        
        # Verify data is visible within transaction
        query_op = Op("db.query", {
            "sql": "SELECT COUNT(*) FROM test_table WHERE name = ?",
            "params": ("test",)
        })
        
        # Use same connection by using same op_id
        query_op.op_id = op.op_id
        result = await self.adaptor.do(query_op)
        assert result[0][0] == 1  # One matching row
        
        # Prepare (commit changes)
        await self.adaptor.prepare(op)
        
        # Verify data is still there after commit
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute("SELECT COUNT(*) FROM test_table WHERE name = ?", ("test",))
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1
    
    async def test_insert_rollback(self):
        """Test database insert rollback."""
        op = Op("db.exec", {
            "sql": "INSERT INTO test_table (name, value) VALUES (?, ?)",
            "params": ("test_rollback", 99)
        })
        
        # Do operation
        await self.adaptor.do(op)
        
        # Undo operation
        await self.adaptor.undo(op)
        
        # Verify data is not there
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute("SELECT COUNT(*) FROM test_table WHERE name = ?", ("test_rollback",))
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 0


class TestIntegration:
    """Test full transaction integration."""
    
    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_file = tempfile.mktemp(suffix='.db')
        
        # Setup database
        conn = sqlite3.connect(self.db_file)
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
        
        self.fs_adaptor = FileSystemAdaptor(self.temp_dir)
        self.db_adaptor = SQLiteAdaptor(self.db_file)
    
    def teardown_method(self):
        """Cleanup test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if os.path.exists(self.db_file):
            os.unlink(self.db_file)
    
    # Define operations using tx_op decorator
    @tx_op(None)  # Will be set in test
    async def write_post_file(self, slug: str, content: str):
        return Op("fs.write", {"path": f"posts/{slug}.md", "data": content})
    
    @tx_op(None)  # Will be set in test
    async def insert_post_record(self, slug: str, title: str, content: str):
        return Op("db.exec", {
            "sql": "INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
            "params": (slug, title, content)
        })
    
    async def test_successful_transaction(self):
        """Test successful multi-resource transaction."""
        # Patch the decorators to use our adaptors
        self.write_post_file.__wrapped__.__globals__['adaptor'] = self.fs_adaptor
        self.insert_post_record.__wrapped__.__globals__['adaptor'] = self.db_adaptor
        
        async with Transaction("create_blog_post") as tx:
            # Register operations manually for this test
            file_op = Op("fs.write", {"path": "posts/hello-world.md", "data": "# Hello World\n\nThis is my first post!"})
            db_op = Op("db.exec", {
                "sql": "INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
                "params": ("hello-world", "Hello World", "This is my first post!")
            })
            
            tx.register(file_op, self.fs_adaptor)
            tx.register(db_op, self.db_adaptor)
        
        # Verify file was created
        file_path = Path(self.temp_dir) / "posts" / "hello-world.md"
        assert file_path.exists()
        assert "Hello World" in file_path.read_text()
        
        # Verify database record was created
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute("SELECT title FROM posts WHERE slug = ?", ("hello-world",))
        result = cursor.fetchone()
        conn.close()
        assert result is not None
        assert result[0] == "Hello World"
    
    async def test_failed_transaction_rollback(self):
        """Test transaction rollback on failure."""
        try:
            async with Transaction("failed_blog_post") as tx:
                # Register operations
                file_op = Op("fs.write", {"path": "posts/failed-post.md", "data": "# Failed Post"})
                db_op = Op("db.exec", {
                    "sql": "INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
                    "params": ("failed-post", "Failed Post", "This should not exist")
                })
                
                tx.register(file_op, self.fs_adaptor)
                tx.register(db_op, self.db_adaptor)
                
                # Simulate failure
                raise ValueError("Simulated failure")
        
        except ValueError:
            pass  # Expected
        
        # Verify file was not created
        file_path = Path(self.temp_dir) / "posts" / "failed-post.md"
        assert not file_path.exists()
        
        # Verify database record was not created
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute("SELECT COUNT(*) FROM posts WHERE slug = ?", ("failed-post",))
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 0


def run_tests():
    """Run all tests."""
    print("Running Tx-Mini framework tests...")
    
    # Test Transaction
    test_tx = TestTransaction()
    test_tx.test_transaction_creation()
    test_tx.test_operation_registration()
    test_tx.test_current_transaction_tracking()
    print("✓ Transaction tests passed")
    
    # Test FileSystemAdaptor
    async def run_fs_tests():
        test_fs = TestFileSystemAdaptor()
        test_fs.setup_method()
        try:
            await test_fs.test_write_operation()
            await test_fs.test_write_rollback()
            await test_fs.test_write_overwrite_rollback()
            await test_fs.test_delete_operation()
            await test_fs.test_delete_rollback()
        finally:
            test_fs.teardown_method()
    
    asyncio.run(run_fs_tests())
    print("✓ FileSystemAdaptor tests passed")
    
    # Test SQLiteAdaptor
    async def run_db_tests():
        test_db = TestSQLiteAdaptor()
        test_db.setup_method()
        try:
            await test_db.test_insert_operation()
            await test_db.test_insert_rollback()
        finally:
            test_db.teardown_method()
    
    asyncio.run(run_db_tests())
    print("✓ SQLiteAdaptor tests passed")
    
    # Test Integration
    async def run_integration_tests():
        test_integration = TestIntegration()
        test_integration.setup_method()
        try:
            await test_integration.test_successful_transaction()
            await test_integration.test_failed_transaction_rollback()
        finally:
            test_integration.teardown_method()
    
    asyncio.run(run_integration_tests())
    print("✓ Integration tests passed")
    
    print("\nAll tests passed! 🎉")


if __name__ == "__main__":
    run_tests()