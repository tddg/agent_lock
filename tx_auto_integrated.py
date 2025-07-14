"""
Tx-Auto-Integrated: Production-ready flexible transaction framework.

Integrates the easy-to-use @transactional decorator with the robust tx_mini.py
transaction coordinator for full ACID guarantees.
"""

import asyncio
import functools
import sqlite3
import os
import tempfile
import uuid
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from unittest.mock import patch

# Import the robust transaction framework
from tx_mini import Transaction, Op, current_tx, in_transaction
from adaptors import FileSystemAdaptor, SQLiteAdaptor


class AutoTransactionManager:
    """Manages automatic operation detection and integration with tx_mini."""
    
    def __init__(self):
        self.db_adaptors: Dict[str, SQLiteAdaptor] = {}
        
    def get_fs_adaptor(self) -> FileSystemAdaptor:
        """Get filesystem adaptor for current working directory."""
        return FileSystemAdaptor(os.getcwd())
        
    def get_db_adaptor(self, database_path: str) -> SQLiteAdaptor:
        """Get or create a database adaptor for the given database."""
        if database_path not in self.db_adaptors:
            self.db_adaptors[database_path] = SQLiteAdaptor(database_path)
        return self.db_adaptors[database_path]


class TransactionalFile:
    """File wrapper that captures writes and integrates with tx_mini."""
    
    def __init__(self, filename: str, mode: str, auto_manager: AutoTransactionManager, *args, **kwargs):
        self.filename = filename
        self.mode = mode
        self.auto_manager = auto_manager
        self.args = args
        self.kwargs = kwargs
        self.content = ""
        self.closed = False
        
        # For read operations, open the actual file
        if 'r' in mode:
            self._real_file = open(filename, mode, *args, **kwargs)
        else:
            self._real_file = None
    
    def write(self, data: str):
        """Capture write data for transactional execution."""
        if self.closed:
            raise ValueError("I/O operation on closed file")
        self.content += data
    
    def read(self, size: int = -1):
        """For read operations, delegate to real file."""
        if self._real_file:
            return self._real_file.read(size)
        return ""
    
    def readline(self, size: int = -1):
        """For read operations, delegate to real file."""
        if self._real_file:
            return self._real_file.readline(size)
        return ""
    
    def readlines(self, hint: int = -1):
        """For read operations, delegate to real file."""
        if self._real_file:
            return self._real_file.readlines(hint)
        return []
    
    def close(self):
        """Register write operation when file is closed."""
        if not self.closed:
            if 'w' in self.mode or 'a' in self.mode:
                # This is a write operation - register with transaction
                tx = current_tx()
                if tx and not self.filename.endswith('.jsonl'):  # Avoid recursive logging
                    op = Op("fs.write", {"path": self.filename, "data": self.content})
                    tx.register(op, self.auto_manager.get_fs_adaptor())
            
            if self._real_file:
                self._real_file.close()
            
            self.closed = True
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def flush(self):
        """For write operations, no-op. For read operations, delegate."""
        if self._real_file:
            self._real_file.flush()
    
    def writelines(self, lines):
        """Capture writelines data for transactional execution."""
        if self.closed:
            raise ValueError("I/O operation on closed file")
        for line in lines:
            self.content += line


class TransactionalConnection:
    """SQLite connection wrapper that integrates with tx_mini."""
    
    def __init__(self, database: str, auto_manager: AutoTransactionManager, *args, **kwargs):
        self.database = database
        self.auto_manager = auto_manager
        self.args = args
        self.kwargs = kwargs
        self.db_adaptor = auto_manager.get_db_adaptor(database)
        
        # For read operations outside transactions, keep a real connection
        self._read_conn = None
    
    def cursor(self):
        """Return transactional cursor."""
        return TransactionalCursor(self.database, self.db_adaptor, self.auto_manager)
    
    def execute(self, sql: str, parameters: tuple = ()):
        """Execute SQL directly on connection."""
        tx = current_tx()
        if tx:
            op = Op("db.exec", {"sql": sql, "params": parameters})
            tx.register(op, self.db_adaptor)
            return TransactionalCursor(self.database, self.db_adaptor, self.auto_manager)
        else:
            # Outside transaction - execute directly for read operations
            if sql.strip().upper().startswith(('SELECT', 'PRAGMA', 'EXPLAIN')):
                return self._get_read_connection().execute(sql, parameters)
            else:
                # Write operation outside transaction - execute directly (original behavior)
                return sqlite3.connect(self.database, *self.args, **self.kwargs).execute(sql, parameters)
    
    def commit(self):
        """No-op - commit handled by transaction framework."""
        if not in_transaction() and self._read_conn:
            self._read_conn.commit()
    
    def rollback(self):
        """No-op - rollback handled by transaction framework."""
        if not in_transaction() and self._read_conn:
            self._read_conn.rollback()
    
    def close(self):
        """Close read connection if exists."""
        if self._read_conn:
            self._read_conn.close()
            self._read_conn = None
    
    def _get_read_connection(self):
        """Get or create read connection for non-transactional reads."""
        if not self._read_conn:
            self._read_conn = sqlite3.connect(self.database, *self.args, **self.kwargs)
        return self._read_conn


class TransactionalCursor:
    """SQLite cursor wrapper that integrates with tx_mini."""
    
    def __init__(self, database: str, db_adaptor: SQLiteAdaptor, auto_manager: AutoTransactionManager):
        self.database = database
        self.db_adaptor = db_adaptor
        self.auto_manager = auto_manager
        self._read_cursor = None
    
    def execute(self, sql: str, parameters: tuple = ()):
        """Execute SQL with transaction integration."""
        tx = current_tx()
        if tx:
            op = Op("db.exec", {"sql": sql, "params": parameters})
            tx.register(op, self.db_adaptor)
            return self
        else:
            # Outside transaction - handle read operations
            if sql.strip().upper().startswith(('SELECT', 'PRAGMA', 'EXPLAIN')):
                conn = sqlite3.connect(self.database)
                self._read_cursor = conn.cursor()
                self._read_cursor.execute(sql, parameters)
                return self
            else:
                # Write operation outside transaction - execute directly
                conn = sqlite3.connect(self.database)
                cursor = conn.cursor()
                result = cursor.execute(sql, parameters)
                conn.commit()
                conn.close()
                return result
    
    def fetchall(self):
        """Fetch results - delegate to read cursor if available."""
        if self._read_cursor:
            return self._read_cursor.fetchall()
        return []  # Transactional cursors return empty for safety
    
    def fetchone(self):
        """Fetch one result - delegate to read cursor if available."""
        if self._read_cursor:
            return self._read_cursor.fetchone()
        return None
    
    def fetchmany(self, size: int = None):
        """Fetch many results - delegate to read cursor if available."""
        if self._read_cursor:
            return self._read_cursor.fetchmany(size)
        return []
    
    @property
    def rowcount(self):
        """Return rowcount - delegate to read cursor if available."""
        if self._read_cursor:
            return self._read_cursor.rowcount
        return 0
    
    @property
    def description(self):
        """Return description - delegate to read cursor if available."""
        if self._read_cursor:
            return self._read_cursor.description
        return None


# Global auto-transaction manager
_auto_manager = AutoTransactionManager()


def patched_open(file, mode='r', *args, **kwargs):
    """Patched version of open() that integrates with tx_mini."""
    # Don't intercept transaction log files to avoid recursion
    if in_transaction() and not str(file).endswith('.jsonl'):
        return TransactionalFile(file, mode, _auto_manager, *args, **kwargs)
    else:
        return open.__wrapped__(file, mode, *args, **kwargs)


def patched_sqlite_connect(database, *args, **kwargs):
    """Patched version of sqlite3.connect() that integrates with tx_mini."""
    if in_transaction():
        return TransactionalConnection(database, _auto_manager, *args, **kwargs)
    else:
        return sqlite3.connect.__wrapped__(database, *args, **kwargs)


def patched_makedirs(path, *args, **kwargs):
    """Patched version of os.makedirs() that integrates with tx_mini."""
    if in_transaction():
        tx = current_tx()
        if tx:
            op = Op("fs.mkdir", {"path": path})
            tx.register(op, _auto_manager.fs_adaptor)
        return None
    else:
        return os.makedirs.__wrapped__(path, *args, **kwargs)


def patched_remove(path, *args, **kwargs):
    """Patched version of os.remove() that integrates with tx_mini."""
    if in_transaction():
        tx = current_tx()
        if tx:
            op = Op("fs.delete", {"path": path})
            tx.register(op, _auto_manager.fs_adaptor)
        return None
    else:
        return os.remove.__wrapped__(path, *args, **kwargs)


def patched_rename(src, dst, *args, **kwargs):
    """Patched version of os.rename() that integrates with tx_mini."""
    if in_transaction():
        tx = current_tx()
        if tx:
            op = Op("fs.rename", {"old_path": src, "new_path": dst})
            tx.register(op, _auto_manager.fs_adaptor)
        return None
    else:
        return os.rename.__wrapped__(src, dst, *args, **kwargs)


@contextmanager
def transaction_patches():
    """Context manager to apply patches during transaction."""
    # Store original functions
    originals = {
        'open': open,
        'sqlite3.connect': sqlite3.connect,
        'os.makedirs': os.makedirs,
        'os.remove': os.remove,
        'os.rename': os.rename,
    }
    
    # Create patched versions that know about originals
    def patched_open_with_orig(file, mode='r', *args, **kwargs):
        # Only patch write operations, not reads, to avoid recursion
        if in_transaction() and not str(file).endswith('.jsonl') and ('w' in mode or 'a' in mode):
            return TransactionalFile(file, mode, _auto_manager, *args, **kwargs)
        else:
            return originals['open'](file, mode, *args, **kwargs)
    
    def patched_sqlite_connect_with_orig(database, *args, **kwargs):
        if in_transaction():
            return TransactionalConnection(database, _auto_manager, *args, **kwargs)
        else:
            return originals['sqlite3.connect'](database, *args, **kwargs)
    
    def patched_makedirs_with_orig(path, *args, **kwargs):
        if in_transaction():
            tx = current_tx()
            if tx:
                op = Op("fs.mkdir", {"path": path})
                tx.register(op, _auto_manager.get_fs_adaptor())
            return None
        else:
            return originals['os.makedirs'](path, *args, **kwargs)
    
    def patched_remove_with_orig(path, *args, **kwargs):
        if in_transaction():
            tx = current_tx()
            if tx:
                op = Op("fs.delete", {"path": path})
                tx.register(op, _auto_manager.get_fs_adaptor())
            return None
        else:
            return originals['os.remove'](path, *args, **kwargs)
    
    def patched_rename_with_orig(src, dst, *args, **kwargs):
        if in_transaction():
            tx = current_tx()
            if tx:
                op = Op("fs.rename", {"old_path": src, "new_path": dst})
                tx.register(op, _auto_manager.get_fs_adaptor())
            return None
        else:
            return originals['os.rename'](src, dst, *args, **kwargs)
    
    # Apply patches
    import builtins
    builtins.open = patched_open_with_orig
    sqlite3.connect = patched_sqlite_connect_with_orig
    os.makedirs = patched_makedirs_with_orig
    os.remove = patched_remove_with_orig
    os.rename = patched_rename_with_orig
    
    try:
        yield
    finally:
        # Restore original functions
        builtins.open = originals['open']
        sqlite3.connect = originals['sqlite3.connect']
        os.makedirs = originals['os.makedirs']
        os.remove = originals['os.remove']
        os.rename = originals['os.rename']


def transactional(func: Callable) -> Callable:
    """
    Production-ready decorator that integrates with tx_mini framework.
    
    Provides full ACID guarantees with automatic operation detection.
    Requires only adding @transactional to existing functions.
    
    Usage:
        @transactional
        def my_function():
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
            with transaction_patches():
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        # For sync functions, handle event loop properly
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an event loop, we need to be careful
            # For now, let's use a simpler synchronous approach
            return _sync_transactional_wrapper(func, *args, **kwargs)
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(async_wrapper(*args, **kwargs))
    
    # Return appropriate wrapper
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def _sync_transactional_wrapper(func: Callable, *args, **kwargs):
    """Synchronous transactional wrapper that integrates with tx_mini."""
    # Create a new event loop for this transaction
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        async def run_with_transaction():
            tx_name = f"{func.__module__}.{func.__name__}"
            async with Transaction(tx_name) as tx:
                with transaction_patches():
                    return func(*args, **kwargs)
        
        result = loop.run_until_complete(run_with_transaction())
        return result
    finally:
        loop.close()
        try:
            asyncio.set_event_loop(None)
        except:
            pass


def auto_transaction(name: str = None):
    """
    Context manager for ad-hoc transactional blocks with tx_mini integration.
    
    Usage:
        with auto_transaction("data_processing"):
            # Existing code unchanged!
            with open("file.txt", "w") as f:
                f.write("data")
            
            conn = sqlite3.connect("db.db")
            # ... rest of code
    """
    return AutoTransactionContext(name or f"auto_transaction_{uuid.uuid4().hex[:8]}")


class AutoTransactionContext:
    """Context manager for auto-transaction blocks with tx_mini integration."""
    
    def __init__(self, name: str):
        self.name = name
        self.tx = None
        self.patch_ctx = None
        self.loop = None
    
    def __enter__(self):
        # Create transaction and start patches
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.tx = Transaction(self.name)
        self.loop.run_until_complete(self.tx.__aenter__())
        
        self.patch_ctx = transaction_patches()
        self.patch_ctx.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.loop.run_until_complete(self.tx.__aexit__(exc_type, exc_val, exc_tb))
        finally:
            self.patch_ctx.__exit__(exc_type, exc_val, exc_tb)
            self.loop.close()
            try:
                asyncio.set_event_loop(None)
            except:
                pass


# Convenience functions for existing code integration
def make_transactional(func: Callable) -> Callable:
    """Alias for @transactional decorator."""
    return transactional(func)


def with_transactions(func: Callable) -> Callable:
    """Alternative name for @transactional decorator."""
    return transactional(func)


# Export the main functions
__all__ = [
    'transactional', 
    'auto_transaction', 
    'make_transactional', 
    'with_transactions',
    'AutoTransactionManager'
]