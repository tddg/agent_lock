"""
Tx-Auto: Drop-in transactional framework for existing agent code.

Provides automatic transaction support with minimal code changes.
Only requires adding @transactional decorator to existing functions.
"""

import asyncio
import functools
import sqlite3
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from unittest.mock import patch

from tx_mini import Transaction, Op, current_tx, in_transaction
from adaptors import FileSystemAdaptor, SQLiteAdaptor


class AutoTransaction:
    """Automatically captures and manages operations in existing code."""
    
    def __init__(self):
        self.fs_adaptor = FileSystemAdaptor(".")
        self.db_adaptor = SQLiteAdaptor("auto_transactions.db")
        self.captured_ops: List[tuple] = []  # (op, adaptor)
        self.active_connections: Dict[str, sqlite3.Connection] = {}
        self.original_functions = {}
        
    def _capture_file_write(self, original_open):
        """Capture file write operations."""
        @functools.wraps(original_open)
        def patched_open(file, mode='r', *args, **kwargs):
            # If we're in a transaction and it's a write operation
            if in_transaction() and ('w' in mode or 'a' in mode):
                # Create a custom file object that captures writes
                return TransactionalFile(file, mode, self.fs_adaptor, *args, **kwargs)
            else:
                return original_open(file, mode, *args, **kwargs)
        return patched_open
    
    def _capture_sqlite_connect(self, original_connect):
        """Capture SQLite connection and operations."""
        @functools.wraps(original_connect)
        def patched_connect(database, *args, **kwargs):
            if in_transaction():
                # Return a transactional connection wrapper
                return TransactionalConnection(database, self.db_adaptor, *args, **kwargs)
            else:
                return original_connect(database, *args, **kwargs)
        return patched_connect
    
    def _capture_os_operations(self, original_func, operation_type):
        """Capture OS file operations."""
        @functools.wraps(original_func)
        def patched_func(*args, **kwargs):
            if in_transaction():
                # Convert to transactional operation
                self._register_os_operation(operation_type, args, kwargs)
                return None  # Don't execute immediately
            else:
                return original_func(*args, **kwargs)
        return patched_func
    
    def _register_os_operation(self, operation_type: str, args: tuple, kwargs: dict):
        """Register OS operations for transactional execution."""
        tx = current_tx()
        if tx:
            if operation_type == "makedirs":
                path = args[0]
                op = Op("fs.mkdir", {"path": path})
                tx.register(op, self.fs_adaptor)
            elif operation_type == "remove":
                path = args[0]
                op = Op("fs.delete", {"path": path})
                tx.register(op, self.fs_adaptor)
            elif operation_type == "rename":
                src, dst = args[0], args[1]
                op = Op("fs.rename", {"old_path": src, "new_path": dst})
                tx.register(op, self.fs_adaptor)
    
    @contextmanager
    def patch_operations(self):
        """Context manager to patch standard library operations."""
        # Store original functions
        self.original_functions = {
            'open': open,
            'sqlite3.connect': sqlite3.connect,
            'os.makedirs': os.makedirs,
            'os.remove': os.remove,
            'os.rename': os.rename,
        }
        
        # Create patches
        patches = [
            patch('builtins.open', self._capture_file_write(open)),
            patch('sqlite3.connect', self._capture_sqlite_connect(sqlite3.connect)),
            patch('os.makedirs', self._capture_os_operations(os.makedirs, "makedirs")),
            patch('os.remove', self._capture_os_operations(os.remove, "remove")),
            patch('os.rename', self._capture_os_operations(os.rename, "rename")),
        ]
        
        # Apply patches
        for p in patches:
            p.start()
        
        try:
            yield
        finally:
            # Remove patches
            for p in patches:
                p.stop()


class TransactionalFile:
    """File object that captures writes for transactional execution."""
    
    def __init__(self, filename, mode, fs_adaptor, *args, **kwargs):
        self.filename = filename
        self.mode = mode
        self.fs_adaptor = fs_adaptor
        self.args = args
        self.kwargs = kwargs
        self.content = ""
        self.closed = False
    
    def write(self, data: str):
        """Capture write data."""
        if self.closed:
            raise ValueError("I/O operation on closed file")
        self.content += data
    
    def close(self):
        """Register write operation when file is closed."""
        if not self.closed:
            tx = current_tx()
            if tx:
                op = Op("fs.write", {"path": self.filename, "data": self.content})
                tx.register(op, self.fs_adaptor)
            self.closed = True
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def flush(self):
        """No-op for transactional files."""
        pass


class TransactionalConnection:
    """SQLite connection wrapper that captures operations."""
    
    def __init__(self, database, db_adaptor, *args, **kwargs):
        self.database = database
        self.db_adaptor = db_adaptor
        self.args = args
        self.kwargs = kwargs
        self.cursors = []
    
    def cursor(self):
        """Return transactional cursor."""
        cursor = TransactionalCursor(self.database, self.db_adaptor)
        self.cursors.append(cursor)
        return cursor
    
    def execute(self, sql, parameters=()):
        """Execute SQL directly on connection."""
        cursor = self.cursor()
        return cursor.execute(sql, parameters)
    
    def commit(self):
        """No-op - commit handled by transaction framework."""
        pass
    
    def rollback(self):
        """No-op - rollback handled by transaction framework."""
        pass
    
    def close(self):
        """No-op - connection management handled by adaptors."""
        pass


class TransactionalCursor:
    """SQLite cursor wrapper that captures operations."""
    
    def __init__(self, database, db_adaptor):
        self.database = database
        self.db_adaptor = db_adaptor
        self.last_result = None
    
    def execute(self, sql, parameters=()):
        """Capture SQL execution."""
        tx = current_tx()
        if tx:
            op = Op("db.exec", {"sql": sql, "params": parameters})
            tx.register(op, self.db_adaptor)
        return self
    
    def fetchall(self):
        """Return empty list for transactional cursors."""
        return []
    
    def fetchone(self):
        """Return None for transactional cursors."""
        return None
    
    def fetchmany(self, size=None):
        """Return empty list for transactional cursors."""
        return []
    
    @property
    def rowcount(self):
        """Return 0 for transactional cursors."""
        return 0


# Global auto-transaction instance
_auto_tx = AutoTransaction()


def transactional(func: Callable) -> Callable:
    """
    Decorator that makes any function transactional with minimal code changes.
    
    Automatically detects and wraps:
    - File operations (open, write, read)
    - SQLite operations (connect, execute, commit)
    - OS operations (makedirs, remove, rename)
    
    Usage:
        @transactional
        def my_agent_function():
            # Existing code unchanged!
            with open("file.txt", "w") as f:
                f.write("data")
            
            conn = sqlite3.connect("db.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO...")
            conn.commit()
            conn.close()
    """
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        # Generate transaction name from function
        tx_name = f"{func.__module__}.{func.__name__}"
        
        async with Transaction(tx_name) as tx:
            with _auto_tx.patch_operations():
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        # For sync functions, handle event loop properly
        try:
            loop = asyncio.get_running_loop()
            # If there's already a running loop, we need to create a task
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(async_wrapper(*args, **kwargs))
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(async_wrapper(*args, **kwargs))
        except ImportError:
            # nest_asyncio not available, use simpler approach
            # Run synchronously with direct transaction management
            return _sync_transactional_wrapper(func, *args, **kwargs)
    
    # Return appropriate wrapper
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def _sync_transactional_wrapper(func: Callable, *args, **kwargs):
    """Synchronous transactional wrapper for functions."""
    # Create a simple event loop for this function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        async def run_with_transaction():
            tx_name = f"{func.__module__}.{func.__name__}"
            async with Transaction(tx_name) as tx:
                with _auto_tx.patch_operations():
                    return func(*args, **kwargs)
        
        result = loop.run_until_complete(run_with_transaction())
        return result
    finally:
        loop.close()
        # Restore previous event loop if any
        try:
            asyncio.set_event_loop(None)
        except:
            pass


def auto_transaction():
    """
    Context manager for ad-hoc transactional blocks.
    
    Usage:
        with auto_transaction():
            # Existing code unchanged!
            with open("file.txt", "w") as f:
                f.write("data")
            
            conn = sqlite3.connect("db.db")
            # ... rest of code
    """
    return _AutoTransactionContext()


class _AutoTransactionContext:
    """Context manager for auto-transaction blocks."""
    
    def __enter__(self):
        # Create transaction and start patches
        self.tx_name = f"auto_transaction_{uuid.uuid4().hex[:8]}"
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.tx = Transaction(self.tx_name)
        self.loop.run_until_complete(self.tx.__aenter__())
        
        self.patch_ctx = _auto_tx.patch_operations()
        self.patch_ctx.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.loop.run_until_complete(self.tx.__aexit__(exc_type, exc_val, exc_tb))
        finally:
            self.patch_ctx.__exit__(exc_type, exc_val, exc_tb)
            self.loop.close()


# Convenience functions for existing code integration
def make_transactional(func: Callable) -> Callable:
    """Alias for @transactional decorator."""
    return transactional(func)


def with_transactions(func: Callable) -> Callable:
    """Alternative name for @transactional decorator."""
    return transactional(func)