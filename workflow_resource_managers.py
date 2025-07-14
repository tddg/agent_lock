#!/usr/bin/env python3

"""
Workflow Resource Managers

Implements resource managers for different types of operations in workflow transactions.
Each manager handles its own transaction semantics while coordinating with the workflow transaction.
"""

import os
import shutil
import sqlite3
import json
import tempfile
import asyncio
import aiohttp
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

from workflow_tx_core import ResourceManager, Operation, OperationType


@dataclass
class FileOperation:
    """Represents a file operation with rollback information."""
    path: str
    operation_type: str  # create, update, delete
    original_content: Optional[str] = None
    backup_path: Optional[str] = None
    created_directories: List[str] = None
    
    def __post_init__(self):
        if self.created_directories is None:
            self.created_directories = []


class FileSystemManager(ResourceManager):
    """
    Manages file system operations within workflow transactions.
    
    Provides copy-on-write semantics and automatic rollback for file operations.
    """
    
    def __init__(self):
        super().__init__("filesystem")
        self.backup_dir = Path(tempfile.mkdtemp(prefix="workflow_fs_backup_"))
        self.file_operations: Dict[str, List[FileOperation]] = {}
    
    async def begin_transaction(self, tx_id: str) -> bool:
        """Begin filesystem transaction."""
        self.file_operations[tx_id] = []
        return True
    
    async def execute_operation(self, operation: Operation) -> Any:
        """Execute a file system operation."""
        tx_id = operation.data.get('tx_id')
        if not tx_id or tx_id not in self.file_operations:
            raise ValueError("Invalid transaction ID for file operation")
        
        if operation.type == OperationType.FILE_CREATE:
            return await self._create_file(tx_id, operation)
        elif operation.type == OperationType.FILE_UPDATE:
            return await self._update_file(tx_id, operation)
        elif operation.type == OperationType.FILE_DELETE:
            return await self._delete_file(tx_id, operation)
        else:
            raise ValueError(f"Unsupported file operation: {operation.type}")
    
    async def _create_file(self, tx_id: str, operation: Operation) -> str:
        """Create a new file."""
        file_path = operation.target
        content = operation.data.get('content', '')
        
        # Check if file already exists
        if os.path.exists(file_path):
            raise FileExistsError(f"File already exists: {file_path}")
        
        # Create directories if needed
        dir_path = os.path.dirname(file_path)
        created_dirs = []
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            created_dirs = self._get_created_directories(dir_path)
        
        # Create file
        with open(file_path, 'w') as f:
            f.write(content)
        
        # Track operation for rollback
        file_op = FileOperation(
            path=file_path,
            operation_type='create',
            created_directories=created_dirs
        )
        self.file_operations[tx_id].append(file_op)
        
        return file_path
    
    async def _update_file(self, tx_id: str, operation: Operation) -> str:
        """Update an existing file."""
        file_path = operation.target
        content = operation.data.get('content', '')
        
        # Backup original content
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Read original content
        with open(file_path, 'r') as f:
            original_content = f.read()
        
        # Create backup
        backup_path = self.backup_dir / f"{tx_id}_{os.path.basename(file_path)}"
        shutil.copy2(file_path, backup_path)
        
        # Update file
        with open(file_path, 'w') as f:
            f.write(content)
        
        # Track operation for rollback
        file_op = FileOperation(
            path=file_path,
            operation_type='update',
            original_content=original_content,
            backup_path=str(backup_path)
        )
        self.file_operations[tx_id].append(file_op)
        
        return file_path
    
    async def _delete_file(self, tx_id: str, operation: Operation) -> str:
        """Delete a file."""
        file_path = operation.target
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Backup file before deletion
        backup_path = self.backup_dir / f"{tx_id}_{os.path.basename(file_path)}"
        shutil.copy2(file_path, backup_path)
        
        # Delete file
        os.remove(file_path)
        
        # Track operation for rollback
        file_op = FileOperation(
            path=file_path,
            operation_type='delete',
            backup_path=str(backup_path)
        )
        self.file_operations[tx_id].append(file_op)
        
        return file_path
    
    def _get_created_directories(self, dir_path: str) -> List[str]:
        """Get list of directories that were created."""
        created = []
        current = Path(dir_path)
        
        while current != current.parent:
            if not current.exists():
                created.insert(0, str(current))
            current = current.parent
        
        return created
    
    async def prepare_commit(self, tx_id: str) -> bool:
        """Prepare to commit filesystem operations."""
        # File operations are already applied, just verify integrity
        if tx_id not in self.file_operations:
            return False
        
        # Verify all files are in expected state
        for file_op in self.file_operations[tx_id]:
            if file_op.operation_type in ['create', 'update']:
                if not os.path.exists(file_op.path):
                    return False
            elif file_op.operation_type == 'delete':
                if os.path.exists(file_op.path):
                    return False
        
        return True
    
    async def commit(self, tx_id: str) -> bool:
        """Commit filesystem operations."""
        if tx_id not in self.file_operations:
            return False
        
        # Clean up backup files
        for file_op in self.file_operations[tx_id]:
            if file_op.backup_path and os.path.exists(file_op.backup_path):
                os.remove(file_op.backup_path)
        
        # Remove transaction record
        del self.file_operations[tx_id]
        return True
    
    async def rollback(self, tx_id: str) -> bool:
        """Rollback filesystem operations."""
        if tx_id not in self.file_operations:
            return False
        
        # Rollback operations in reverse order
        for file_op in reversed(self.file_operations[tx_id]):
            try:
                if file_op.operation_type == 'create':
                    # Remove created file
                    if os.path.exists(file_op.path):
                        os.remove(file_op.path)
                    
                    # Remove created directories (in reverse order)
                    for dir_path in reversed(file_op.created_directories):
                        if os.path.exists(dir_path) and not os.listdir(dir_path):
                            os.rmdir(dir_path)
                
                elif file_op.operation_type == 'update':
                    # Restore from backup
                    if file_op.backup_path and os.path.exists(file_op.backup_path):
                        shutil.copy2(file_op.backup_path, file_op.path)
                
                elif file_op.operation_type == 'delete':
                    # Restore deleted file
                    if file_op.backup_path and os.path.exists(file_op.backup_path):
                        shutil.copy2(file_op.backup_path, file_op.path)
                
            except Exception as e:
                # Log error but continue rollback
                print(f"Error during rollback of {file_op.path}: {e}")
        
        # Clean up
        del self.file_operations[tx_id]
        return True
    
    async def get_status(self, tx_id: str) -> Dict[str, Any]:
        """Get status of filesystem transaction."""
        if tx_id not in self.file_operations:
            return {"status": "not_found"}
        
        operations = self.file_operations[tx_id]
        return {
            "status": "active",
            "operation_count": len(operations),
            "operations": [
                {
                    "path": op.path,
                    "type": op.operation_type,
                    "has_backup": bool(op.backup_path)
                }
                for op in operations
            ]
        }


class DatabaseManager(ResourceManager):
    """
    Manages database operations within workflow transactions.
    
    Uses savepoints for SQLite transactions and supports rollback.
    """
    
    def __init__(self, db_path: str):
        super().__init__("database")
        self.db_path = db_path
        self.connections: Dict[str, sqlite3.Connection] = {}
        self.savepoints: Dict[str, str] = {}
    
    async def begin_transaction(self, tx_id: str) -> bool:
        """Begin database transaction."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("BEGIN")
            
            # Create savepoint
            savepoint_name = f"sp_{tx_id.replace('-', '_')}"
            conn.execute(f"SAVEPOINT {savepoint_name}")
            
            self.connections[tx_id] = conn
            self.savepoints[tx_id] = savepoint_name
            return True
        except Exception as e:
            print(f"Failed to begin database transaction: {e}")
            return False
    
    async def execute_operation(self, operation: Operation) -> Any:
        """Execute a database operation."""
        tx_id = operation.data.get('tx_id')
        if not tx_id or tx_id not in self.connections:
            raise ValueError("Invalid transaction ID for database operation")
        
        conn = self.connections[tx_id]
        
        if operation.type == OperationType.DB_INSERT:
            return await self._insert_record(conn, operation)
        elif operation.type == OperationType.DB_UPDATE:
            return await self._update_record(conn, operation)
        elif operation.type == OperationType.DB_DELETE:
            return await self._delete_record(conn, operation)
        else:
            raise ValueError(f"Unsupported database operation: {operation.type}")
    
    async def _insert_record(self, conn: sqlite3.Connection, operation: Operation) -> int:
        """Insert a database record."""
        table = operation.target
        data = operation.data.get('record_data', {})
        
        columns = list(data.keys())
        placeholders = ['?' for _ in columns]
        values = list(data.values())
        
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        cursor = conn.execute(sql, values)
        return cursor.lastrowid
    
    async def _update_record(self, conn: sqlite3.Connection, operation: Operation) -> int:
        """Update database records."""
        table = operation.target
        data = operation.data.get('record_data', {})
        where_clause = operation.data.get('where_clause', "")
        where_params = operation.data.get('where_params', [])
        
        set_clause = ', '.join([f"{col} = ?" for col in data.keys()])
        values = list(data.values()) + where_params
        
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        cursor = conn.execute(sql, values)
        return cursor.rowcount
    
    async def _delete_record(self, conn: sqlite3.Connection, operation: Operation) -> int:
        """Delete database records."""
        table = operation.target
        where_clause = operation.data.get('where_clause', "")
        where_params = operation.data.get('where_params', [])
        
        sql = f"DELETE FROM {table} WHERE {where_clause}"
        cursor = conn.execute(sql, where_params)
        return cursor.rowcount
    
    async def prepare_commit(self, tx_id: str) -> bool:
        """Prepare to commit database transaction."""
        if tx_id not in self.connections:
            return False
        
        # For SQLite, we can't really prepare (no 2PC support)
        # Just verify connection is still valid
        try:
            conn = self.connections[tx_id]
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    async def commit(self, tx_id: str) -> bool:
        """Commit database transaction."""
        if tx_id not in self.connections:
            return False
        
        try:
            conn = self.connections[tx_id]
            
            # Release savepoint (commits the work)
            savepoint = self.savepoints[tx_id]
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            
            # Commit the transaction
            conn.commit()
            conn.close()
            
            # Clean up
            del self.connections[tx_id]
            del self.savepoints[tx_id]
            return True
        except Exception as e:
            print(f"Failed to commit database transaction: {e}")
            return False
    
    async def rollback(self, tx_id: str) -> bool:
        """Rollback database transaction."""
        if tx_id not in self.connections:
            return False
        
        try:
            conn = self.connections[tx_id]
            
            # Rollback to savepoint
            savepoint = self.savepoints[tx_id]
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            
            # Close connection
            conn.rollback()
            conn.close()
            
            # Clean up
            del self.connections[tx_id]
            del self.savepoints[tx_id]
            return True
        except Exception as e:
            print(f"Failed to rollback database transaction: {e}")
            return False
    
    async def get_status(self, tx_id: str) -> Dict[str, Any]:
        """Get status of database transaction."""
        if tx_id not in self.connections:
            return {"status": "not_found"}
        
        return {
            "status": "active",
            "database": self.db_path,
            "savepoint": self.savepoints.get(tx_id)
        }


class APIManager(ResourceManager):
    """
    Manages external API calls within workflow transactions.
    
    Uses compensation patterns for rollback since HTTP calls can't be truly rolled back.
    """
    
    def __init__(self):
        super().__init__("api")
        self.api_calls: Dict[str, List[Dict[str, Any]]] = {}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def begin_transaction(self, tx_id: str) -> bool:
        """Begin API transaction."""
        self.api_calls[tx_id] = []
        if not self.session:
            self.session = aiohttp.ClientSession()
        return True
    
    async def execute_operation(self, operation: Operation) -> Any:
        """Execute an API call."""
        tx_id = operation.data.get('tx_id')
        if not tx_id or tx_id not in self.api_calls:
            raise ValueError("Invalid transaction ID for API operation")
        
        # Extract API call parameters
        url = operation.target
        method = operation.data.get('method', 'GET')
        headers = operation.data.get('headers', {})
        data = operation.data.get('payload')
        compensation_data = operation.data.get('compensation')
        
        # Make API call
        async with self.session.request(method, url, headers=headers, json=data) as response:
            response_data = await response.json() if response.content_type == 'application/json' else await response.text()
            
            # Track call for potential compensation
            api_call_record = {
                "url": url,
                "method": method,
                "request_data": data,
                "response_data": response_data,
                "status_code": response.status,
                "compensation": compensation_data
            }
            self.api_calls[tx_id].append(api_call_record)
            
            if response.status >= 400:
                raise Exception(f"API call failed: {response.status} - {response_data}")
            
            return response_data
    
    async def prepare_commit(self, tx_id: str) -> bool:
        """Prepare to commit API operations."""
        # APIs are already called, can't really prepare
        return tx_id in self.api_calls
    
    async def commit(self, tx_id: str) -> bool:
        """Commit API operations."""
        if tx_id not in self.api_calls:
            return False
        
        # APIs are already executed, just clean up
        del self.api_calls[tx_id]
        return True
    
    async def rollback(self, tx_id: str) -> bool:
        """Rollback API operations using compensation."""
        if tx_id not in self.api_calls:
            return False
        
        # Execute compensation calls in reverse order
        for api_call in reversed(self.api_calls[tx_id]):
            compensation = api_call.get('compensation')
            if compensation:
                try:
                    # Execute compensation API call
                    comp_url = compensation.get('url')
                    comp_method = compensation.get('method', 'POST')
                    comp_data = compensation.get('data')
                    comp_headers = compensation.get('headers', {})
                    
                    async with self.session.request(comp_method, comp_url, 
                                                  headers=comp_headers, json=comp_data) as response:
                        if response.status >= 400:
                            print(f"Compensation call failed: {response.status}")
                except Exception as e:
                    print(f"Error in API compensation: {e}")
        
        # Clean up
        del self.api_calls[tx_id]
        return True
    
    async def get_status(self, tx_id: str) -> Dict[str, Any]:
        """Get status of API transaction."""
        if tx_id not in self.api_calls:
            return {"status": "not_found"}
        
        calls = self.api_calls[tx_id]
        return {
            "status": "active",
            "call_count": len(calls),
            "calls": [
                {
                    "url": call["url"],
                    "method": call["method"],
                    "status_code": call["status_code"],
                    "has_compensation": bool(call.get("compensation"))
                }
                for call in calls
            ]
        }
    
    async def close(self):
        """Close the API session."""
        if self.session:
            await self.session.close()


# Export resource managers
__all__ = [
    'FileSystemManager',
    'DatabaseManager', 
    'APIManager',
    'FileOperation'
]