"""
Resource adaptors for the Tx-Mini framework.

Provides FileSystemAdaptor and SQLiteAdaptor implementations.
"""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from tx_mini import Op, ResourceAdaptor


class FileSystemAdaptor:
    """
    Filesystem adaptor using copy-on-write pattern for safe rollback.
    
    Operations:
    - fs.write: Write data to a file
    - fs.delete: Delete a file
    - fs.rename: Rename a file
    - fs.mkdir: Create a directory
    """
    
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir).resolve()
        self.temp_files: Dict[str, str] = {}  # op_id -> temp_file_path
        self.backed_up_files: Dict[str, str] = {}  # op_id -> backup_file_path
    
    def _get_full_path(self, relative_path: str) -> Path:
        """Get full path, ensuring it's within root_dir."""
        full_path = (self.root_dir / relative_path).resolve()
        
        # Security check: ensure path is within root_dir
        try:
            full_path.relative_to(self.root_dir)
        except ValueError:
            raise ValueError(f"Path {relative_path} is outside root directory {self.root_dir}")
        
        return full_path
    
    async def do(self, op: Op) -> Any:
        """Execute filesystem operation using copy-on-write."""
        kind = op.kind
        args = op.args
        
        if kind == "fs.write":
            return await self._do_write(op, args["path"], args["data"])
        elif kind == "fs.delete":
            return await self._do_delete(op, args["path"])
        elif kind == "fs.rename":
            return await self._do_rename(op, args["old_path"], args["new_path"])
        elif kind == "fs.mkdir":
            return await self._do_mkdir(op, args["path"])
        else:
            raise ValueError(f"Unknown filesystem operation: {kind}")
    
    async def undo(self, op: Op) -> None:
        """Undo filesystem operation."""
        kind = op.kind
        
        if kind == "fs.write":
            await self._undo_write(op)
        elif kind == "fs.delete":
            await self._undo_delete(op)
        elif kind == "fs.rename":
            await self._undo_rename(op)
        elif kind == "fs.mkdir":
            await self._undo_mkdir(op)
    
    async def prepare(self, op: Op) -> bool:
        """Prepare filesystem operation (make changes durable)."""
        kind = op.kind
        
        if kind == "fs.write":
            return await self._prepare_write(op)
        elif kind == "fs.delete":
            return await self._prepare_delete(op)
        elif kind == "fs.rename":
            return await self._prepare_rename(op)
        elif kind == "fs.mkdir":
            return await self._prepare_mkdir(op)
        
        return True
    
    # Write operations
    async def _do_write(self, op: Op, path: str, data: Any) -> None:
        """Write data to temporary file."""
        target_path = self._get_full_path(path)
        
        # Create parent directories if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup existing file if it exists
        if target_path.exists():
            backup_dir = Path(tempfile.gettempdir()) / "tx_backup"
            backup_dir.mkdir(exist_ok=True)
            backup_path = backup_dir / f"{op.op_id}_backup"
            shutil.copy2(target_path, backup_path)
            self.backed_up_files[op.op_id] = str(backup_path)
        
        # Write to temporary file
        temp_dir = Path(tempfile.gettempdir()) / "tx_temp"
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / f"{op.op_id}_temp"
        
        if isinstance(data, str):
            temp_path.write_text(data)
        else:
            temp_path.write_bytes(data)
        
        self.temp_files[op.op_id] = str(temp_path)
    
    async def _prepare_write(self, op: Op) -> bool:
        """Move temporary file to final location."""
        if op.op_id not in self.temp_files:
            return True
        
        temp_path = Path(self.temp_files[op.op_id])
        target_path = self._get_full_path(op.args["path"])
        
        # Atomic move (rename)
        shutil.move(str(temp_path), str(target_path))
        
        # Clean up temp file reference
        del self.temp_files[op.op_id]
        
        return True
    
    async def _undo_write(self, op: Op) -> None:
        """Undo write operation."""
        # Remove temp file if still exists
        if op.op_id in self.temp_files:
            temp_path = Path(self.temp_files[op.op_id])
            if temp_path.exists():
                temp_path.unlink()
            del self.temp_files[op.op_id]
        
        # Restore backup if exists
        if op.op_id in self.backed_up_files:
            backup_path = Path(self.backed_up_files[op.op_id])
            target_path = self._get_full_path(op.args["path"])
            
            if backup_path.exists():
                shutil.move(str(backup_path), str(target_path))
            
            del self.backed_up_files[op.op_id]
        else:
            # No backup means file didn't exist, so delete it
            target_path = self._get_full_path(op.args["path"])
            if target_path.exists():
                target_path.unlink()
    
    # Delete operations
    async def _do_delete(self, op: Op, path: str) -> None:
        """Delete file (backup first)."""
        target_path = self._get_full_path(path)
        
        if target_path.exists():
            # Backup the file
            backup_dir = Path(tempfile.gettempdir()) / "tx_backup"
            backup_dir.mkdir(exist_ok=True)
            backup_path = backup_dir / f"{op.op_id}_backup"
            shutil.copy2(target_path, backup_path)
            self.backed_up_files[op.op_id] = str(backup_path)
    
    async def _prepare_delete(self, op: Op) -> bool:
        """Actually delete the file."""
        target_path = self._get_full_path(op.args["path"])
        if target_path.exists():
            target_path.unlink()
        return True
    
    async def _undo_delete(self, op: Op) -> None:
        """Restore deleted file from backup."""
        if op.op_id in self.backed_up_files:
            backup_path = Path(self.backed_up_files[op.op_id])
            target_path = self._get_full_path(op.args["path"])
            
            if backup_path.exists():
                shutil.move(str(backup_path), str(target_path))
            
            del self.backed_up_files[op.op_id]
    
    # Rename operations
    async def _do_rename(self, op: Op, old_path: str, new_path: str) -> None:
        """Rename operation (backup old file)."""
        old_full_path = self._get_full_path(old_path)
        new_full_path = self._get_full_path(new_path)
        
        if old_full_path.exists():
            # Backup if new path exists
            if new_full_path.exists():
                backup_dir = Path(tempfile.gettempdir()) / "tx_backup"
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f"{op.op_id}_new_backup"
                shutil.copy2(new_full_path, backup_path)
                self.backed_up_files[f"{op.op_id}_new"] = str(backup_path)
            
            # Store original location for undo
            self.backed_up_files[f"{op.op_id}_old"] = str(old_full_path)
    
    async def _prepare_rename(self, op: Op) -> bool:
        """Execute the rename."""
        old_full_path = self._get_full_path(op.args["old_path"])
        new_full_path = self._get_full_path(op.args["new_path"])
        
        if old_full_path.exists():
            new_full_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_full_path), str(new_full_path))
        
        return True
    
    async def _undo_rename(self, op: Op) -> None:
        """Undo rename operation."""
        old_full_path = self._get_full_path(op.args["old_path"])
        new_full_path = self._get_full_path(op.args["new_path"])
        
        # Move file back to original location
        if new_full_path.exists():
            shutil.move(str(new_full_path), str(old_full_path))
        
        # Restore file that was overwritten at new location
        backup_key = f"{op.op_id}_new"
        if backup_key in self.backed_up_files:
            backup_path = Path(self.backed_up_files[backup_key])
            if backup_path.exists():
                shutil.move(str(backup_path), str(new_full_path))
            del self.backed_up_files[backup_key]
        
        # Clean up old location backup reference
        old_backup_key = f"{op.op_id}_old"
        if old_backup_key in self.backed_up_files:
            del self.backed_up_files[old_backup_key]
    
    # Directory operations
    async def _do_mkdir(self, op: Op, path: str) -> None:
        """Create directory (track for undo)."""
        target_path = self._get_full_path(path)
        # Just track that we need to create this directory
        # Don't actually create it until prepare
    
    async def _prepare_mkdir(self, op: Op) -> bool:
        """Actually create the directory."""
        target_path = self._get_full_path(op.args["path"])
        target_path.mkdir(parents=True, exist_ok=True)
        return True
    
    async def _undo_mkdir(self, op: Op) -> None:
        """Remove created directory if empty."""
        target_path = self._get_full_path(op.args["path"])
        
        try:
            # Only remove if empty (don't want to remove directories with other content)
            if target_path.exists() and target_path.is_dir():
                target_path.rmdir()
        except OSError:
            # Directory not empty, leave it
            pass


class SQLiteAdaptor:
    """
    SQLite adaptor using savepoints for transaction management.
    
    Operations:
    - db.exec: Execute SQL statement
    - db.query: Execute SQL query (read-only)
    """
    
    def __init__(self, database_path: str):
        self.database_path = database_path
        self.connections: Dict[str, sqlite3.Connection] = {}
        self.savepoints: Dict[str, str] = {}  # op_id -> savepoint_name
    
    def _get_connection(self, op_id: str) -> sqlite3.Connection:
        """Get or create connection for this operation."""
        if op_id not in self.connections:
            conn = sqlite3.connect(self.database_path)
            conn.execute("BEGIN")
            self.connections[op_id] = conn
        
        return self.connections[op_id]
    
    async def do(self, op: Op) -> Any:
        """Execute database operation within a savepoint."""
        kind = op.kind
        args = op.args
        
        conn = self._get_connection(op.op_id)
        savepoint_name = f"sp_{op.op_id.replace('-', '_')}"
        
        # Create savepoint
        conn.execute(f"SAVEPOINT {savepoint_name}")
        self.savepoints[op.op_id] = savepoint_name
        
        try:
            if kind == "db.exec":
                sql = args["sql"]
                params = args.get("params", ())
                cursor = conn.execute(sql, params)
                return cursor.rowcount
            elif kind == "db.query":
                sql = args["sql"]
                params = args.get("params", ())
                cursor = conn.execute(sql, params)
                return cursor.fetchall()
            else:
                raise ValueError(f"Unknown database operation: {kind}")
        
        except Exception as e:
            # Rollback to savepoint on error
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            raise e
    
    async def undo(self, op: Op) -> None:
        """Rollback to savepoint."""
        if op.op_id in self.savepoints:
            conn = self.connections.get(op.op_id)
            savepoint_name = self.savepoints[op.op_id]
            
            if conn:
                try:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                except sqlite3.Error:
                    # Savepoint might not exist anymore, rollback entire transaction
                    conn.rollback()
                finally:
                    conn.close()
            
            del self.savepoints[op.op_id]
            if op.op_id in self.connections:
                del self.connections[op.op_id]
    
    async def prepare(self, op: Op) -> bool:
        """Release savepoint (make changes visible)."""
        if op.op_id in self.savepoints:
            conn = self.connections.get(op.op_id)
            savepoint_name = self.savepoints[op.op_id]
            
            if conn:
                # Release savepoint (changes become part of main transaction)
                conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                conn.commit()
                conn.close()
            
            del self.savepoints[op.op_id]
            if op.op_id in self.connections:
                del self.connections[op.op_id]
        
        return True  # SQLite supports 2PC via savepoints