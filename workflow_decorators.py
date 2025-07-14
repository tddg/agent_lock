#!/usr/bin/env python3

"""
Workflow-Aware Decorators - Proof of Concept

Provides easy-to-use decorators that make existing code automatically transactional
with minimal changes required.
"""

import asyncio
import builtins
import contextvars
import sqlite3
import uuid
from functools import wraps
from typing import Callable, List, Dict, Any, Optional, Union
import inspect
import time
from pathlib import Path

# Import existing workflow framework
from workflow_tx_core import WorkflowTransaction, Operation, OperationType, WorkflowError
from workflow_resource_managers import FileSystemManager, DatabaseManager


class WorkflowContext:
    """Manages workflow context across function calls."""
    
    _current_workflow: contextvars.ContextVar[Optional[WorkflowTransaction]] = \
        contextvars.ContextVar('current_workflow', default=None)
    
    @classmethod
    def get_current(cls) -> Optional[WorkflowTransaction]:
        """Get the current workflow transaction."""
        return cls._current_workflow.get()
    
    @classmethod
    def set_current(cls, workflow: WorkflowTransaction):
        """Set the current workflow transaction."""
        cls._current_workflow.set(workflow)
    
    @classmethod
    def clear_current(cls):
        """Clear the current workflow transaction."""
        cls._current_workflow.set(None)


class TrackedFile:
    """Wrapper for file objects that tracks operations."""
    
    def __init__(self, file_obj, operation: Operation):
        self._file = file_obj
        self._operation = operation
        self._written = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._file.__exit__(exc_type, exc_val, exc_tb)
    
    def write(self, data):
        """Track write operations."""
        result = self._file.write(data)
        
        # Update operation data with content
        if not self._written:
            self._operation.data['content'] = data
            self._written = True
        else:
            # Append to existing content
            existing = self._operation.data.get('content', '')
            self._operation.data['content'] = existing + data
        
        return result
    
    def read(self, size=-1):
        """Track read operations."""
        return self._file.read(size)
    
    def __getattr__(self, name):
        """Delegate other methods to the wrapped file."""
        return getattr(self._file, name)


class FileOperationTracker:
    """Tracks file system operations by monkey-patching built-ins."""
    
    def __init__(self):
        self.original_open = None
        self.is_patched = False
    
    def patch(self):
        """Replace built-in open with tracking version."""
        if not self.is_patched:
            self.original_open = builtins.open
            builtins.open = self.tracked_open
            self.is_patched = True
    
    def unpatch(self):
        """Restore original open function."""
        if self.is_patched and self.original_open:
            builtins.open = self.original_open
            self.is_patched = False
    
    def tracked_open(self, filename, mode='r', **kwargs):
        """Open file with operation tracking."""
        # Prevent tracking of our own log files to avoid recursion
        if isinstance(filename, (str, Path)) and 'workflow_tx_log' in str(filename):
            return self.original_open(filename, mode, **kwargs)
        
        # Get current workflow
        current_workflow = WorkflowContext.get_current()
        
        if current_workflow is None:
            # No workflow context, use original open
            return self.original_open(filename, mode, **kwargs)
        
        # Determine operation type based on mode
        operation_type = self._determine_operation_type(filename, mode)
        
        # Create operation
        operation = Operation(
            id=f"file_{uuid.uuid4().hex[:8]}",
            type=operation_type,
            resource_type="filesystem",
            target=str(filename),
            data={
                "tx_id": current_workflow.id,
                "mode": mode,
                "kwargs": kwargs
            }
        )
        
        # Add operation to workflow
        current_workflow.add_operation(operation)
        
        # Open file and return tracked wrapper
        file_obj = self.original_open(filename, mode, **kwargs)
        return TrackedFile(file_obj, operation)
    
    def _determine_operation_type(self, filename, mode):
        """Determine operation type based on file mode."""
        if 'w' in mode:
            # Check if file exists to determine create vs update
            if Path(filename).exists():
                return OperationType.FILE_UPDATE
            else:
                return OperationType.FILE_CREATE
        elif 'a' in mode:
            return OperationType.FILE_UPDATE
        else:
            # Read mode - we'll treat this as a read operation
            # For simplicity, we'll use FILE_CREATE as a generic operation
            return OperationType.FILE_CREATE


class DatabaseOperationTracker:
    """Tracks SQLite database operations."""
    
    def __init__(self):
        self.original_connect = None
        self.original_execute = None
        self.is_patched = False
    
    def patch(self):
        """Patch SQLite module for tracking."""
        if not self.is_patched:
            self.original_connect = sqlite3.connect
            sqlite3.connect = self.tracked_connect
            self.is_patched = True
    
    def unpatch(self):
        """Restore original SQLite functions."""
        if self.is_patched and self.original_connect:
            sqlite3.connect = self.original_connect
            self.is_patched = False
    
    def tracked_connect(self, database, **kwargs):
        """Connect to database with tracking."""
        conn = self.original_connect(database, **kwargs)
        
        # Get current workflow
        current_workflow = WorkflowContext.get_current()
        if current_workflow:
            # Wrap connection to track operations
            return TrackedConnection(conn, current_workflow, database)
        
        return conn


class TrackedConnection:
    """Wrapper for database connections that tracks operations."""
    
    def __init__(self, connection, workflow: WorkflowTransaction, database_path: str):
        self._conn = connection
        self._workflow = workflow
        self._database_path = database_path
        self.original_execute = connection.execute
        
        # Replace execute method with tracking version
        connection.execute = self.tracked_execute
    
    def tracked_execute(self, sql, parameters=()):
        """Track SQL execution."""
        # Determine operation type from SQL
        operation_type = self._determine_operation_type(sql)
        
        # Create operation
        operation = Operation(
            id=f"db_{uuid.uuid4().hex[:8]}",
            type=operation_type,
            resource_type="database",
            target=self._database_path,
            data={
                "tx_id": self._workflow.id,
                "sql": sql,
                "parameters": parameters
            }
        )
        
        # Add to workflow
        self._workflow.add_operation(operation)
        
        # Execute original SQL
        return self.original_execute(sql, parameters)
    
    def _determine_operation_type(self, sql: str) -> OperationType:
        """Determine operation type from SQL statement."""
        sql_upper = sql.upper().strip()
        if sql_upper.startswith('INSERT'):
            return OperationType.DB_INSERT
        elif sql_upper.startswith('UPDATE'):
            return OperationType.DB_UPDATE
        elif sql_upper.startswith('DELETE'):
            return OperationType.DB_DELETE
        else:
            # For SELECT, CREATE, etc., use INSERT as default
            return OperationType.DB_INSERT
    
    def __getattr__(self, name):
        """Delegate other methods to the wrapped connection."""
        return getattr(self._conn, name)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)


class OperationDetector:
    """Automatically detects and tracks operations in user code."""
    
    def __init__(self):
        self.file_tracker = FileOperationTracker()
        self.db_tracker = DatabaseOperationTracker()
        self.active_trackers = []
    
    def patch_modules(self, modules_to_track: List[str]):
        """Patch specified modules for operation tracking."""
        if "file" in modules_to_track or "all" in modules_to_track:
            self.file_tracker.patch()
            self.active_trackers.append(self.file_tracker)
        
        if "database" in modules_to_track or "all" in modules_to_track:
            self.db_tracker.patch()
            self.active_trackers.append(self.db_tracker)
    
    def unpatch_modules(self):
        """Restore original module behavior."""
        for tracker in self.active_trackers:
            tracker.unpatch()
        self.active_trackers.clear()


def auto_transactional(
    name: Optional[str] = None,
    timeout: int = 60,
    rollback_on_error: bool = True,
    track_operations: List[str] = ["all"],
    exclude_operations: List[str] = [],
    debug: bool = False
):
    """
    Make a function automatically transactional with minimal code changes.
    
    Args:
        name: Custom workflow name (default: function name)
        timeout: Transaction timeout in seconds
        rollback_on_error: Whether to auto-rollback on exceptions
        track_operations: List of operation types to track ("all", "file", "database")
        exclude_operations: List of operation types to exclude
        debug: Enable debug logging
    """
    
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Create workflow transaction
            workflow_name = name or f"{func.__module__}.{func.__name__}"
            wtx = WorkflowTransaction(workflow_name, f"Auto-transactional: {func.__name__}")
            
            if debug:
                print(f"🔄 Starting workflow: {workflow_name}")
            
            # Set up operation detection
            detector = OperationDetector()
            
            try:
                # Set workflow context
                WorkflowContext.set_current(wtx)
                
                # Set up resource managers
                await _setup_resource_managers(wtx, track_operations, debug)
                
                # Patch modules for operation tracking
                modules_to_patch = _determine_modules_to_patch(track_operations, exclude_operations)
                detector.patch_modules(modules_to_patch)
                
                if debug:
                    print(f"📡 Tracking operations: {modules_to_patch}")
                
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                if debug:
                    print(f"✅ Function completed, executing workflow with {len(wtx.operations)} operations")
                
                # Execute workflow transaction
                await wtx.execute()
                
                if debug:
                    print(f"🎉 Workflow completed successfully")
                
                return result
                
            except Exception as e:
                if debug:
                    print(f"❌ Workflow failed: {e}")
                
                if rollback_on_error:
                    if debug:
                        print(f"🔄 Rolling back workflow...")
                    await wtx.rollback()
                    if debug:
                        print(f"↩️  Rollback completed")
                
                raise WorkflowError(
                    step_name=f"{func.__name__}",
                    error=e,
                    completed_steps=wtx.completed_operations.copy()
                )
            finally:
                # Clean up
                detector.unpatch_modules()
                WorkflowContext.clear_current()
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, run in async context
            try:
                # Try to get the current event loop
                loop = asyncio.get_running_loop()
                # If we're already in an event loop, create a task
                return asyncio.create_task(async_wrapper(*args, **kwargs))
            except RuntimeError:
                # No event loop running, safe to use asyncio.run
                return asyncio.run(async_wrapper(*args, **kwargs))
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            # For sync functions, we need to handle the async carefully
            def real_sync_wrapper(*args, **kwargs):
                try:
                    # Check if we're in an async context
                    loop = asyncio.get_running_loop()
                    # We can't use asyncio.run() from within an event loop
                    # Instead, we'll run synchronously but still use the workflow
                    return sync_execute_with_workflow(func, args, kwargs, 
                                                    workflow_name or f"{func.__module__}.{func.__name__}",
                                                    track_operations, rollback_on_error, debug)
                except RuntimeError:
                    # No event loop, safe to use full async version
                    return asyncio.run(async_wrapper(*args, **kwargs))
            
            return real_sync_wrapper
    
    return decorator


def sync_execute_with_workflow(func, args, kwargs, workflow_name, track_operations, rollback_on_error, debug):
    """Execute a sync function with workflow transaction (simplified version)."""
    if debug:
        print(f"🔄 Starting sync workflow: {workflow_name}")
    
    # For simplicity in this proof of concept, we'll use a minimal approach
    # that doesn't require async execution for sync functions
    detector = OperationDetector()
    
    try:
        # Patch modules for operation tracking
        modules_to_patch = _determine_modules_to_patch(track_operations, [])
        detector.patch_modules(modules_to_patch)
        
        if debug:
            print(f"📡 Tracking operations: {modules_to_patch}")
        
        # Execute function
        result = func(*args, **kwargs)
        
        if debug:
            print(f"✅ Sync function completed successfully")
        
        return result
        
    except Exception as e:
        if debug:
            print(f"❌ Sync workflow failed: {e}")
        
        # For sync version, we can't do full rollback easily
        # This is a limitation of the simplified approach
        if rollback_on_error:
            if debug:
                print(f"⚠️  Note: Sync rollback is limited in this proof of concept")
        
        raise e
    finally:
        # Clean up
        detector.unpatch_modules()


def _determine_modules_to_patch(track_operations: List[str], exclude_operations: List[str]) -> List[str]:
    """Determine which modules to patch based on configuration."""
    module_mapping = {
        "file": ["file"],
        "database": ["database"],
        "db": ["database"],
        "all": ["file", "database"]
    }
    
    modules = set()
    for op_type in track_operations:
        modules.update(module_mapping.get(op_type, []))
    
    # Remove excluded modules
    for exclude in exclude_operations:
        modules.discard(exclude)
    
    return list(modules)


async def _setup_resource_managers(wtx: WorkflowTransaction, track_operations: List[str], debug: bool = False):
    """Set up resource managers based on tracked operations."""
    if "all" in track_operations or "file" in track_operations:
        fs_manager = FileSystemManager()
        wtx.register_resource_manager("filesystem", fs_manager)
        if debug:
            print("📁 Registered FileSystemManager")
    
    if "all" in track_operations or "database" in track_operations or "db" in track_operations:
        # For proof of concept, use a default database manager
        # In production, this would be more sophisticated
        db_manager = DatabaseManager(":memory:")
        wtx.register_resource_manager("database", db_manager)
        if debug:
            print("🗄️  Registered DatabaseManager")


# Convenience aliases
workflow_atomic = auto_transactional
transactional = auto_transactional


if __name__ == "__main__":
    # Simple test
    print("🧪 Testing workflow decorators...")
    
    @auto_transactional(debug=True)
    def test_function():
        # Create a file
        with open("test.txt", "w") as f:
            f.write("Hello, workflow!")
        
        return "success"
    
    try:
        result = test_function()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")