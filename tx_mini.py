"""
Tx-Mini: A lightweight transactional programming framework for multi-agent workflows.

Provides ACID-style safety for SQLite, filesystem, and extensible resources using
2PC or Saga patterns with automatic fallback based on adaptor capabilities.
"""

import asyncio
import json
import os
import sqlite3
import shutil
import tempfile
import uuid
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Union
from functools import wraps
import threading


class Op:
    """Represents a single operation in a transaction."""
    
    def __init__(self, kind: str, args: Dict[str, Any], op_id: Optional[str] = None):
        self.kind = kind
        self.args = args
        self.op_id = op_id or str(uuid.uuid4())
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "args": self.args,
            "op_id": self.op_id,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Op':
        op = cls(data["kind"], data["args"], data["op_id"])
        op.timestamp = data["timestamp"]
        return op


class ResourceAdaptor(Protocol):
    """Protocol for resource adaptors that can participate in transactions."""
    
    async def do(self, op: Op) -> Any:
        """Execute the operation. Should be idempotent."""
        ...
    
    async def undo(self, op: Op) -> None:
        """Undo the operation. Should be idempotent."""
        ...
    
    async def prepare(self, op: Op) -> bool:
        """Prepare for commit. Returns True if 2PC is supported, False for Saga."""
        ...


class TransactionError(Exception):
    """Base exception for transaction-related errors."""
    pass


class CommitError(TransactionError):
    """Raised when a transaction commit fails."""
    pass


class AbortError(TransactionError):
    """Raised when a transaction abort fails."""
    pass


# Global thread-local storage for current transaction
_local = threading.local()


def current_tx() -> Optional['Transaction']:
    """Get the current transaction in this thread."""
    return getattr(_local, 'current_tx', None)


def in_transaction() -> bool:
    """Check if we're currently in a transaction."""
    return current_tx() is not None


class Transaction:
    """
    Core transaction coordinator with JSON logging and 2PC/Saga support.
    """
    
    def __init__(self, name: str = "", log_dir: str = "~/tx_log"):
        self.name = name
        self.tx_id = str(uuid.uuid4())
        self.log_dir = Path(log_dir).expanduser()
        self.log_file = self.log_dir / f"{self.tx_id}.jsonl"
        
        # Operation tracking
        self.ops: List[Op] = []
        self.adaptors: Dict[str, ResourceAdaptor] = {}  # op_id -> adaptor
        
        # State tracking
        self.state = "ACTIVE"  # ACTIVE, PREPARING, COMMITTED, ABORTED
        self.supports_2pc = True  # Will be determined during prepare phase
        
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def register(self, op: Op, adaptor: ResourceAdaptor) -> None:
        """Register an operation with its adaptor."""
        self.ops.append(op)
        self.adaptors[op.op_id] = adaptor
        self._log_entry("REGISTER", op.to_dict())
    
    def _log_entry(self, event: str, data: Dict[str, Any]) -> None:
        """Write a log entry to the transaction log."""
        entry = {
            "tx_id": self.tx_id,
            "event": event,
            "timestamp": time.time(),
            "data": data
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno())  # Force write to disk
    
    async def __aenter__(self) -> 'Transaction':
        """Enter the transaction context."""
        # Set as current transaction
        _local.current_tx = self
        self._log_entry("BEGIN", {"name": self.name})
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the transaction context and run coordinator."""
        try:
            if exc_type is not None:
                # Exception occurred, abort transaction
                await self.abort()
            else:
                # Normal exit, commit transaction
                await self.commit()
        finally:
            # Clear current transaction
            _local.current_tx = None
    
    async def commit(self) -> None:
        """Commit the transaction using 2PC or Saga pattern."""
        if self.state != "ACTIVE":
            raise CommitError(f"Cannot commit transaction in state: {self.state}")
        
        self._log_entry("COMMIT_START", {})
        
        try:
            # Phase 1: Check if all adaptors support 2PC
            supports_2pc = await self._check_2pc_support()
            
            if supports_2pc:
                await self._commit_2pc()
            else:
                await self._commit_saga()
                
            self.state = "COMMITTED"
            self._log_entry("COMMIT_SUCCESS", {})
            
        except Exception as e:
            self.state = "ABORTED"
            self._log_entry("COMMIT_FAILED", {"error": str(e)})
            # Attempt rollback
            await self._rollback()
            raise CommitError(f"Transaction commit failed: {e}") from e
    
    async def abort(self) -> None:
        """Abort the transaction and rollback changes."""
        if self.state in ("COMMITTED", "ABORTED"):
            return  # Already finalized
        
        self._log_entry("ABORT_START", {})
        
        try:
            await self._rollback()
            self.state = "ABORTED"
            self._log_entry("ABORT_SUCCESS", {})
        except Exception as e:
            self._log_entry("ABORT_FAILED", {"error": str(e)})
            raise AbortError(f"Transaction abort failed: {e}") from e
    
    async def _check_2pc_support(self) -> bool:
        """Check if all adaptors support 2PC."""
        for op in self.ops:
            adaptor = self.adaptors[op.op_id]
            try:
                # We can't actually call prepare yet since we haven't done the operations
                # Instead, check if the adaptor has a working prepare method
                # For now, assume all our adaptors support 2PC
                if hasattr(adaptor, 'prepare') and callable(adaptor.prepare):
                    continue
                else:
                    return False
            except NotImplementedError:
                return False
            except Exception:
                # Other errors during prepare indicate actual failures
                return False
        return True
    
    async def _commit_2pc(self) -> None:
        """Commit using Two-Phase Commit protocol."""
        self._log_entry("2PC_PREPARE_START", {})
        
        # Phase 1: Execute and prepare all operations
        prepared_ops = []
        try:
            for op in self.ops:
                adaptor = self.adaptors[op.op_id]
                # First execute the operation
                await adaptor.do(op)
                self._log_entry("2PC_EXECUTED", {"op_id": op.op_id})
                
                # Then prepare it (make it durable)
                success = await adaptor.prepare(op)
                if not success:
                    raise CommitError(f"Prepare failed for operation {op.op_id}")
                prepared_ops.append(op.op_id)
                self._log_entry("2PC_PREPARED", {"op_id": op.op_id})
            
            # Phase 2: All prepared successfully, commit is now guaranteed
            self._log_entry("2PC_COMMIT_START", {})
            # In 2PC, prepare phase makes changes durable, so we're done
            
        except Exception as e:
            # Rollback any operations that were prepared
            self._log_entry("2PC_PREPARE_FAILED", {"error": str(e), "prepared_ops": prepared_ops})
            await self._rollback_prepared(prepared_ops)
            raise
    
    async def _commit_saga(self) -> None:
        """Commit using Saga pattern (do operations, compensate on failure)."""
        self._log_entry("SAGA_START", {})
        
        executed_ops = []
        try:
            # Execute all operations in order
            for op in self.ops:
                adaptor = self.adaptors[op.op_id]
                await adaptor.do(op)
                executed_ops.append(op.op_id)
                self._log_entry("SAGA_EXECUTED", {"op_id": op.op_id})
            
            # In Saga pattern, we execute immediately and then prepare to make durable
            for op in self.ops:
                adaptor = self.adaptors[op.op_id]
                try:
                    await adaptor.prepare(op)
                except NotImplementedError:
                    # Adaptor doesn't support prepare, that's fine for Saga
                    pass
            
            self._log_entry("SAGA_SUCCESS", {})
            
        except Exception as e:
            # Compensate (undo) all executed operations in reverse order
            self._log_entry("SAGA_FAILED", {"error": str(e), "executed_ops": executed_ops})
            await self._compensate(executed_ops)
            raise
    
    async def _rollback(self) -> None:
        """Rollback all operations."""
        # Undo operations in reverse order
        for op in reversed(self.ops):
            try:
                adaptor = self.adaptors[op.op_id]
                await adaptor.undo(op)
                self._log_entry("ROLLBACK_OP", {"op_id": op.op_id})
            except Exception as e:
                self._log_entry("ROLLBACK_OP_FAILED", {"op_id": op.op_id, "error": str(e)})
                # Continue rolling back other operations
    
    async def _rollback_prepared(self, prepared_ops: List[str]) -> None:
        """Rollback operations that were prepared in 2PC."""
        for op_id in reversed(prepared_ops):
            try:
                op = next(op for op in self.ops if op.op_id == op_id)
                adaptor = self.adaptors[op_id]
                await adaptor.undo(op)
                self._log_entry("2PC_ROLLBACK_OP", {"op_id": op_id})
            except Exception as e:
                self._log_entry("2PC_ROLLBACK_OP_FAILED", {"op_id": op_id, "error": str(e)})
    
    async def _compensate(self, executed_ops: List[str]) -> None:
        """Compensate (undo) executed operations in Saga."""
        for op_id in reversed(executed_ops):
            try:
                op = next(op for op in self.ops if op.op_id == op_id)
                adaptor = self.adaptors[op_id]
                await adaptor.undo(op)
                self._log_entry("SAGA_COMPENSATE_OP", {"op_id": op_id})
            except Exception as e:
                self._log_entry("SAGA_COMPENSATE_OP_FAILED", {"op_id": op_id, "error": str(e)})


def tx_op(adaptor: ResourceAdaptor):
    """
    Decorator that captures function calls as operations and executes them
    within the current transaction context.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get operation details from function call
            op = Op(
                kind=f"{func.__module__}.{func.__name__}",
                args={"args": args, "kwargs": kwargs}
            )
            
            tx = current_tx()
            if tx is not None:
                # We're in a transaction, register the operation
                tx.register(op, adaptor)
                # In Saga mode, we execute immediately; in 2PC mode, we defer to commit
                # For simplicity in Phase 1, we'll defer execution to commit phase
                return None
            else:
                # No transaction, execute immediately (best-effort mode)
                return await adaptor.do(op)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we'll store the operation for later execution
            op = Op(
                kind=f"{func.__module__}.{func.__name__}",
                args={"args": args, "kwargs": kwargs}
            )
            
            tx = current_tx()
            if tx is not None:
                tx.register(op, adaptor)
                return None
            else:
                # No transaction, execute immediately using asyncio
                return asyncio.run(adaptor.do(op))
        
        # Return appropriate wrapper based on whether original function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator