#!/usr/bin/env python3

"""
Workflow-Level Transaction Framework - Core Implementation

Provides workflow-level transaction boundaries that match agentic workflow patterns.
Supports cross-resource coordination, prompt-driven boundaries, and intelligent rollback.
"""

import asyncio
import uuid
import json
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Union, Tuple
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Status of a workflow transaction."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class OperationType(Enum):
    """Types of operations in a workflow."""
    FILE_CREATE = "file_create"
    FILE_UPDATE = "file_update"
    FILE_DELETE = "file_delete"
    DB_INSERT = "db_insert"
    DB_UPDATE = "db_update"
    DB_DELETE = "db_delete"
    API_CALL = "api_call"
    CLOUD_UPLOAD = "cloud_upload"
    EMAIL_SEND = "email_send"
    CUSTOM = "custom"


@dataclass
class Operation:
    """Represents a single operation within a workflow."""
    id: str
    type: OperationType
    resource_type: str
    target: str
    data: Dict[str, Any]
    compensation: Optional[Callable] = None
    executed: bool = False
    result: Optional[Any] = None
    error: Optional[Exception] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass 
class Checkpoint:
    """Represents a rollback checkpoint in a workflow."""
    name: str
    timestamp: float
    completed_operations: List[str]
    workflow_state: Dict[str, Any]


@dataclass
class WorkflowPlan:
    """Represents a parsed workflow plan from user prompt."""
    name: str
    operations: List[Operation] = field(default_factory=list)
    requires_confirmation: bool = False
    estimated_duration: Optional[float] = None
    risk_level: str = "low"  # low, medium, high
    description: str = ""


class ResourceManager(ABC):
    """Abstract base class for resource managers."""
    
    def __init__(self, name: str):
        self.name = name
        self.active_transactions: Dict[str, Any] = {}
    
    @abstractmethod
    async def begin_transaction(self, tx_id: str) -> bool:
        """Begin a transaction for this resource type."""
        pass
    
    @abstractmethod
    async def execute_operation(self, operation: Operation) -> Any:
        """Execute an operation within the transaction."""
        pass
    
    @abstractmethod
    async def prepare_commit(self, tx_id: str) -> bool:
        """Prepare to commit (2PC phase 1)."""
        pass
    
    @abstractmethod
    async def commit(self, tx_id: str) -> bool:
        """Commit the transaction (2PC phase 2)."""
        pass
    
    @abstractmethod
    async def rollback(self, tx_id: str) -> bool:
        """Rollback the transaction."""
        pass
    
    @abstractmethod
    async def get_status(self, tx_id: str) -> Dict[str, Any]:
        """Get transaction status for this resource."""
        pass


class WorkflowError(Exception):
    """Exception raised when workflow execution fails."""
    
    def __init__(self, step_name: str, error: Exception, completed_steps: List[str]):
        self.step_name = step_name
        self.error = error
        self.completed_steps = completed_steps
        super().__init__(f"Workflow failed at step: {step_name}")
    
    def user_friendly_message(self) -> str:
        """Generate user-friendly error message."""
        return f"""
❌ Workflow failed at step: {self.step_name}

✅ Successfully completed:
{chr(10).join(f'  - {step}' for step in self.completed_steps)}

❌ Failed step: {self.step_name}
Error: {self.error}

🔄 All changes have been rolled back.
Would you like to:
1. Retry the workflow
2. Modify the workflow
3. Execute partial workflow (up to failure point)
"""


class WorkflowTransaction:
    """
    Core workflow transaction coordinator.
    
    Manages cross-resource transactions with ACID guarantees at the workflow level.
    """
    
    def __init__(self, name: str, description: str = ""):
        self.id = str(uuid.uuid4())
        self.name = name
        self.description = description
        self.status = WorkflowStatus.PENDING
        self.operations: List[Operation] = []
        self.completed_operations: List[str] = []
        self.resource_managers: Dict[str, ResourceManager] = {}
        self.checkpoints: List[Checkpoint] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.error: Optional[Exception] = None
        
        # Workflow state
        self.workflow_state: Dict[str, Any] = {}
        
        # Logging
        self.log_file = self._create_log_file()
    
    def _create_log_file(self) -> Path:
        """Create log file for this workflow transaction."""
        log_dir = Path.home() / "workflow_tx_log"
        log_dir.mkdir(exist_ok=True)
        return log_dir / f"{self.id}.jsonl"
    
    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """Log workflow event."""
        event = {
            "timestamp": time.time(),
            "workflow_id": self.id,
            "workflow_name": self.name,
            "event_type": event_type,
            "data": data
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event) + "\n")
        
        logger.info(f"Workflow {self.name}: {event_type} - {data}")
    
    def register_resource_manager(self, resource_type: str, manager: ResourceManager):
        """Register a resource manager for this workflow."""
        self.resource_managers[resource_type] = manager
        self._log_event("resource_registered", {"resource_type": resource_type})
    
    def add_operation(self, operation: Operation):
        """Add an operation to the workflow."""
        self.operations.append(operation)
        self._log_event("operation_added", {
            "operation_id": operation.id,
            "type": operation.type.value,
            "target": operation.target
        })
    
    def add_checkpoint(self, name: str):
        """Add a rollback checkpoint."""
        checkpoint = Checkpoint(
            name=name,
            timestamp=time.time(),
            completed_operations=self.completed_operations.copy(),
            workflow_state=self.workflow_state.copy()
        )
        self.checkpoints.append(checkpoint)
        self._log_event("checkpoint_created", {"name": name})
    
    async def execute(self) -> Any:
        """Execute the entire workflow atomically."""
        self.status = WorkflowStatus.EXECUTING
        self.start_time = time.time()
        self._log_event("workflow_started", {"operation_count": len(self.operations)})
        
        try:
            # Phase 1: Begin transactions on all resource managers
            await self._begin_all_transactions()
            
            # Phase 2: Execute all operations
            results = await self._execute_all_operations()
            
            # Phase 3: Two-phase commit
            await self._two_phase_commit()
            
            self.status = WorkflowStatus.COMPLETED
            self.end_time = time.time()
            
            self._log_event("workflow_completed", {
                "duration": self.end_time - self.start_time,
                "operations_executed": len(self.completed_operations)
            })
            
            return results
            
        except Exception as e:
            self.error = e
            self.status = WorkflowStatus.FAILED
            
            self._log_event("workflow_failed", {
                "error": str(e),
                "completed_operations": len(self.completed_operations)
            })
            
            # Automatic rollback on failure
            await self.rollback()
            
            # Raise workflow error with context
            raise WorkflowError(
                step_name=getattr(e, 'operation_id', 'unknown'),
                error=e,
                completed_steps=self.completed_operations.copy()
            )
    
    async def _begin_all_transactions(self):
        """Begin transactions on all resource managers."""
        for resource_type, manager in self.resource_managers.items():
            success = await manager.begin_transaction(self.id)
            if not success:
                raise Exception(f"Failed to begin transaction on {resource_type}")
            
            self._log_event("resource_transaction_started", {
                "resource_type": resource_type
            })
    
    async def _execute_all_operations(self) -> List[Any]:
        """Execute all operations in sequence."""
        results = []
        
        for operation in self.operations:
            try:
                # Find appropriate resource manager
                manager = self.resource_managers.get(operation.resource_type)
                if not manager:
                    raise Exception(f"No resource manager for {operation.resource_type}")
                
                # Execute operation
                self._log_event("operation_starting", {
                    "operation_id": operation.id,
                    "type": operation.type.value
                })
                
                result = await manager.execute_operation(operation)
                operation.executed = True
                operation.result = result
                results.append(result)
                
                self.completed_operations.append(operation.id)
                
                self._log_event("operation_completed", {
                    "operation_id": operation.id,
                    "result_summary": str(result)[:100] if result else None
                })
                
            except Exception as e:
                operation.error = e
                e.operation_id = operation.id  # Add context for error handling
                raise e
        
        return results
    
    async def _two_phase_commit(self):
        """Perform two-phase commit across all resource managers."""
        # Phase 1: Prepare
        self._log_event("commit_phase1_starting", {})
        
        failed_resources = []
        for resource_type, manager in self.resource_managers.items():
            try:
                prepared = await manager.prepare_commit(self.id)
                if not prepared:
                    failed_resources.append(resource_type)
            except Exception as e:
                failed_resources.append(resource_type)
                logger.error(f"Prepare failed for {resource_type}: {e}")
        
        if failed_resources:
            raise Exception(f"Prepare phase failed for: {failed_resources}")
        
        # Phase 2: Commit
        self._log_event("commit_phase2_starting", {})
        
        for resource_type, manager in self.resource_managers.items():
            try:
                await manager.commit(self.id)
                self._log_event("resource_committed", {"resource_type": resource_type})
            except Exception as e:
                logger.error(f"Commit failed for {resource_type}: {e}")
                # Note: At this point, we're in an inconsistent state
                # This requires manual intervention or advanced recovery
                raise e
    
    async def rollback(self):
        """Rollback the entire workflow."""
        self.status = WorkflowStatus.ROLLING_BACK
        self._log_event("rollback_starting", {})
        
        # Rollback in reverse order of resource registration
        for resource_type, manager in reversed(list(self.resource_managers.items())):
            try:
                await manager.rollback(self.id)
                self._log_event("resource_rolled_back", {"resource_type": resource_type})
            except Exception as e:
                logger.error(f"Rollback failed for {resource_type}: {e}")
                # Continue rolling back other resources
        
        self.status = WorkflowStatus.ROLLED_BACK
        self.end_time = time.time()
        
        self._log_event("workflow_rolled_back", {
            "operations_rolled_back": len(self.completed_operations)
        })
    
    async def rollback_to_checkpoint(self, checkpoint_name: str):
        """Rollback to a specific checkpoint."""
        checkpoint = next((cp for cp in self.checkpoints if cp.name == checkpoint_name), None)
        if not checkpoint:
            raise ValueError(f"Checkpoint '{checkpoint_name}' not found")
        
        self._log_event("checkpoint_rollback_starting", {"checkpoint": checkpoint_name})
        
        # Rollback operations executed after checkpoint
        operations_to_rollback = [
            op for op in self.operations 
            if op.id in self.completed_operations and 
               op.id not in checkpoint.completed_operations
        ]
        
        # Execute compensation actions for operations to rollback
        for operation in reversed(operations_to_rollback):
            if operation.compensation:
                try:
                    await operation.compensation()
                    self._log_event("operation_compensated", {"operation_id": operation.id})
                except Exception as e:
                    logger.error(f"Compensation failed for {operation.id}: {e}")
        
        # Restore workflow state
        self.completed_operations = checkpoint.completed_operations.copy()
        self.workflow_state = checkpoint.workflow_state.copy()
        
        self._log_event("checkpoint_rollback_completed", {"checkpoint": checkpoint_name})
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive workflow status."""
        resource_statuses = {}
        for resource_type, manager in self.resource_managers.items():
            try:
                resource_statuses[resource_type] = await manager.get_status(self.id)
            except Exception as e:
                resource_statuses[resource_type] = {"error": str(e)}
        
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "progress": {
                "completed": len(self.completed_operations),
                "total": len(self.operations),
                "percentage": len(self.completed_operations) / len(self.operations) * 100 if self.operations else 0
            },
            "duration": (time.time() - self.start_time) if self.start_time else 0,
            "checkpoints": len(self.checkpoints),
            "resources": resource_statuses,
            "error": str(self.error) if self.error else None
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if exc_type is not None:
            # Exception occurred, rollback
            await self.rollback()
        else:
            # Normal completion, execute
            await self.execute()
        return False  # Don't suppress exceptions


@asynccontextmanager
async def workflow_transaction(name: str, description: str = ""):
    """
    Context manager for workflow transactions.
    
    Usage:
        async with workflow_transaction("blog_creation") as wtx:
            wtx.add_operation(...)
            # Operations are executed atomically when context exits
    """
    wtx = WorkflowTransaction(name, description)
    try:
        yield wtx
    except Exception as e:
        await wtx.rollback()
        raise
    else:
        await wtx.execute()


# Decorator for workflow functions
def workflow_transactional(name: str, description: str = ""):
    """
    Decorator to make a function execute within a workflow transaction.
    
    Usage:
        @workflow_transactional("blog_creation")
        async def create_blog_workflow():
            # All operations here are atomic
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async with workflow_transaction(name, description) as wtx:
                # Inject workflow transaction into function
                return await func(wtx, *args, **kwargs)
        return wrapper
    return decorator


# Export main classes and functions
__all__ = [
    'WorkflowTransaction',
    'ResourceManager', 
    'Operation',
    'OperationType',
    'WorkflowStatus',
    'WorkflowError',
    'WorkflowPlan',
    'Checkpoint',
    'workflow_transaction',
    'workflow_transactional'
]