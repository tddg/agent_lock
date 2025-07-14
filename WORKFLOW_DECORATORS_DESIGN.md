# Workflow-Aware Decorator Design

## 🎯 Problem Statement

The current workflow transaction framework requires **significant code modifications** to existing agent code:
- Converting simple function calls to complex Operation objects
- Manual resource manager setup
- Verbose boilerplate for every operation
- High learning curve and migration cost

## 🚀 Solution: Progressive Enhancement with Decorators

Provide **multiple levels of integration** that allow developers to adopt workflow transactions incrementally:

1. **Level 0**: Automatic detection with zero code changes
2. **Level 1**: Simple decorators with minimal changes  
3. **Level 2**: Smart proxies for enhanced control
4. **Level 3**: Full Operation API for maximum control (existing)

## 🏗️ Architecture Overview

```
Existing Code → Decorator → Auto-Detection → Resource Tracking → Workflow Transaction
     ↓              ↓            ↓               ↓                    ↓
def create_post()  @workflow    [file ops,     [FileManager,      WorkflowTx
                   async def    db ops,        DBManager,         (automatic)
                   create_post  api calls]     APIManager]
```

### Key Design Principles

1. **Zero Breaking Changes**: Existing code continues to work unchanged
2. **Progressive Enhancement**: Add features incrementally as needed
3. **Automatic Detection**: Framework detects operations without explicit configuration
4. **Smart Defaults**: Sensible behavior with minimal configuration
5. **Escape Hatches**: Full control available when needed

## 📋 API Design

### Level 0: Automatic Detection Decorator

**Zero code changes required** - just add a decorator:

```python
from workflow_decorators import auto_transactional

# Before: Regular function
def create_blog_post(title, content):
    post_file = f"posts/{title}.md"
    
    with open(post_file, 'w') as f:
        f.write(f"# {title}\n\n{content}")
    
    conn = sqlite3.connect("blog.db")
    conn.execute("INSERT INTO posts (title, file_path) VALUES (?, ?)", 
                 (title, post_file))
    conn.commit()
    conn.close()
    
    send_email("New post published!")
    
    return post_file

# After: Same code + decorator
@auto_transactional
def create_blog_post(title, content):
    # Exact same code - framework automatically detects:
    # - File operations (open, write)
    # - Database operations (sqlite3 calls)  
    # - Network operations (email sending)
    post_file = f"posts/{title}.md"
    
    with open(post_file, 'w') as f:        # Auto-tracked
        f.write(f"# {title}\n\n{content}")
    
    conn = sqlite3.connect("blog.db")      # Auto-tracked
    conn.execute("INSERT INTO posts (title, file_path) VALUES (?, ?)", 
                 (title, post_file))
    conn.commit()
    conn.close()
    
    send_email("New post published!")      # Auto-tracked
    
    return post_file
```

**How it works:**
- Decorator wraps function in workflow transaction
- Monkey-patches standard library modules (sqlite3, open, requests, etc.)
- Automatically detects and tracks operations
- Provides rollback for supported operations

### Level 1: Enhanced Control with Configuration

**Minimal changes** - add configuration for better control:

```python
@auto_transactional(
    name="blog_creation",
    timeout=30,
    rollback_on_error=True,
    track_operations=["file", "database", "email"]
)
async def create_blog_post(title, content):
    # Same existing code with enhanced transaction control
    pass
```

**Configuration Options:**
```python
@auto_transactional(
    name="workflow_name",              # Custom workflow name
    timeout=60,                        # Transaction timeout in seconds
    rollback_on_error=True,            # Auto-rollback on exceptions
    track_operations=["all"],          # Which operations to track
    exclude_operations=["logging"],    # Operations to exclude
    checkpoints=["after_db"],          # Auto-checkpoint creation
    retry_policy={"max_retries": 3},   # Retry configuration
    compensation_handlers={            # Custom rollback handlers
        "email": custom_email_rollback
    }
)
```

### Level 2: Smart Proxy API

**Slightly modified calls** - use smart proxies for enhanced features:

```python
@workflow_aware
async def create_blog_post(title, content, wtx):
    # Framework injects 'wtx' parameter with smart proxies
    post_file = f"posts/{title}.md"
    
    # Smart proxies that look like normal operations
    await wtx.file.write(post_file, f"# {title}\n\n{content}")
    
    await wtx.db.execute("blog.db", 
                        "INSERT INTO posts VALUES (?, ?)", 
                        (title, post_file))
    
    await wtx.email.send(
        to="subscribers@blog.com",
        subject=f"New post: {title}",
        compensation=lambda: wtx.email.send("admin@blog.com", "Rollback occurred")
    )
    
    # Add checkpoint
    wtx.checkpoint("post_created")
    
    return post_file
```

**Smart Proxy Features:**
- `wtx.file.*` - File operations with automatic rollback
- `wtx.db.*` - Database operations with savepoints
- `wtx.api.*` - HTTP calls with compensation
- `wtx.email.*` - Email sending with tracking
- `wtx.checkpoint()` - Manual checkpoint creation

### Level 3: Hybrid Approach

**Mix automatic and explicit** - combine approaches as needed:

```python
@auto_transactional(track_operations=["file", "database"])
async def create_blog_post(title, content, wtx=None):
    # Most operations are automatic
    post_file = f"posts/{title}.md"
    
    with open(post_file, 'w') as f:        # Auto-tracked
        f.write(f"# {title}\n\n{content}")
    
    conn = sqlite3.connect("blog.db")      # Auto-tracked  
    conn.execute("INSERT INTO posts VALUES (?, ?)", (title, post_file))
    conn.commit()
    conn.close()
    
    # But use explicit control for complex operations
    if wtx:
        await wtx.api.call(
            url="https://cdn.example.com/invalidate",
            method="POST", 
            data={"path": post_file},
            compensation={
                "url": "https://cdn.example.com/refresh", 
                "method": "POST",
                "data": {"path": post_file}
            }
        )
    
    return post_file
```

## 🔧 Implementation Strategy

### 1. Operation Detection Engine

**AutoDetector** class that identifies operations through:

```python
class OperationDetector:
    """Automatically detects operations in user code."""
    
    def __init__(self):
        self.tracked_modules = {
            'builtins': FileOperationTracker(),      # open(), file I/O
            'sqlite3': DatabaseOperationTracker(),   # SQLite operations
            'requests': HTTPOperationTracker(),      # HTTP requests
            'smtplib': EmailOperationTracker(),      # Email sending
            'subprocess': ProcessOperationTracker(), # Process execution
            'shutil': FileOperationTracker(),        # File utilities
            'pathlib': FileOperationTracker(),       # Path operations
        }
    
    def patch_modules(self, modules_to_track):
        """Monkey-patch specified modules for operation tracking."""
        for module_name in modules_to_track:
            if module_name in self.tracked_modules:
                self.tracked_modules[module_name].patch()
    
    def unpatch_modules(self):
        """Restore original module behavior."""
        for tracker in self.tracked_modules.values():
            tracker.unpatch()
```

### 2. Smart Resource Trackers

**Individual trackers** for each resource type:

```python
class FileOperationTracker:
    """Tracks file system operations."""
    
    def __init__(self):
        self.original_open = builtins.open
        self.operations = []
    
    def patch(self):
        """Replace built-in open with tracking version."""
        builtins.open = self.tracked_open
    
    def tracked_open(self, filename, mode='r', **kwargs):
        """Open file with operation tracking."""
        # Determine operation type
        operation_type = self._determine_operation_type(mode)
        
        # Track the operation
        operation = Operation(
            id=f"file_{uuid.uuid4().hex[:8]}",
            type=operation_type,
            resource_type="filesystem",
            target=filename,
            data={"mode": mode, "kwargs": kwargs}
        )
        
        # Add to current workflow if exists
        current_workflow = WorkflowContext.get_current()
        if current_workflow:
            current_workflow.add_operation(operation)
        
        # Return wrapped file object for further tracking
        return TrackedFile(self.original_open(filename, mode, **kwargs), operation)
    
    def _determine_operation_type(self, mode):
        if 'w' in mode or 'a' in mode:
            return OperationType.FILE_CREATE if 'w' in mode else OperationType.FILE_UPDATE
        return OperationType.FILE_READ
```

### 3. Workflow Context Management

**Thread-local context** to track current workflow:

```python
import contextvars
from typing import Optional

class WorkflowContext:
    """Manages workflow context across async calls."""
    
    _current_workflow: contextvars.ContextVar[Optional['WorkflowTransaction']] = \
        contextvars.ContextVar('current_workflow', default=None)
    
    @classmethod
    def get_current(cls) -> Optional['WorkflowTransaction']:
        """Get the current workflow transaction."""
        return cls._current_workflow.get()
    
    @classmethod
    def set_current(cls, workflow: 'WorkflowTransaction'):
        """Set the current workflow transaction."""
        cls._current_workflow.set(workflow)
    
    @classmethod
    def clear_current(cls):
        """Clear the current workflow transaction."""
        cls._current_workflow.set(None)
```

### 4. Decorator Implementation

**Core decorator** that wraps functions:

```python
from functools import wraps
from typing import Callable, List, Dict, Any, Optional
import inspect
import asyncio

def auto_transactional(
    name: Optional[str] = None,
    timeout: int = 60,
    rollback_on_error: bool = True,
    track_operations: List[str] = ["all"],
    exclude_operations: List[str] = [],
    checkpoints: List[str] = [],
    retry_policy: Optional[Dict[str, Any]] = None,
    compensation_handlers: Optional[Dict[str, Callable]] = None
):
    """
    Make a function automatically transactional with minimal code changes.
    
    Args:
        name: Custom workflow name (default: function name)
        timeout: Transaction timeout in seconds
        rollback_on_error: Whether to auto-rollback on exceptions
        track_operations: List of operation types to track ("all", "file", "database", etc.)
        exclude_operations: List of operation types to exclude
        checkpoints: Auto-create checkpoints at specified points
        retry_policy: Retry configuration for failed operations
        compensation_handlers: Custom rollback handlers for specific operations
    """
    
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Create workflow transaction
            workflow_name = name or f"{func.__module__}.{func.__name__}"
            wtx = WorkflowTransaction(workflow_name, f"Auto-transactional: {func.__name__}")
            
            # Set up operation detection
            detector = OperationDetector()
            
            try:
                # Set workflow context
                WorkflowContext.set_current(wtx)
                
                # Patch modules for operation tracking
                modules_to_patch = _determine_modules_to_patch(track_operations, exclude_operations)
                detector.patch_modules(modules_to_patch)
                
                # Set up resource managers
                await _setup_resource_managers(wtx, track_operations)
                
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Execute workflow transaction
                await wtx.execute()
                
                return result
                
            except Exception as e:
                if rollback_on_error:
                    await wtx.rollback()
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
            return asyncio.run(async_wrapper(*args, **kwargs))
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def _determine_modules_to_patch(track_operations: List[str], exclude_operations: List[str]) -> List[str]:
    """Determine which modules to patch based on configuration."""
    all_modules = ["builtins", "sqlite3", "requests", "smtplib", "subprocess", "shutil", "pathlib"]
    
    if "all" in track_operations:
        modules = all_modules.copy()
    else:
        module_mapping = {
            "file": ["builtins", "shutil", "pathlib"],
            "database": ["sqlite3"],
            "http": ["requests"],
            "email": ["smtplib"],
            "process": ["subprocess"]
        }
        
        modules = []
        for op_type in track_operations:
            modules.extend(module_mapping.get(op_type, []))
    
    # Remove excluded modules
    for exclude in exclude_operations:
        if exclude in modules:
            modules.remove(exclude)
    
    return list(set(modules))

async def _setup_resource_managers(wtx: WorkflowTransaction, track_operations: List[str]):
    """Set up resource managers based on tracked operations."""
    if "all" in track_operations or "file" in track_operations:
        wtx.register_resource_manager("filesystem", FileSystemManager())
    
    if "all" in track_operations or "database" in track_operations:
        # Auto-detect database files and create managers
        # This could be enhanced to detect database URLs, etc.
        wtx.register_resource_manager("database", DatabaseManager(":memory:"))
    
    if "all" in track_operations or "http" in track_operations:
        wtx.register_resource_manager("api", APIManager())
    
    if "all" in track_operations or "email" in track_operations:
        wtx.register_resource_manager("email", EmailManager())
```

## 🧪 Usage Examples

### Example 1: Blog Publishing System

```python
# Zero changes to existing code
@auto_transactional
def publish_blog_post(title, content, tags):
    # Create post file
    post_path = f"posts/{slugify(title)}.md"
    with open(post_path, 'w') as f:
        f.write(f"# {title}\n\n{content}\n\nTags: {', '.join(tags)}")
    
    # Update database
    conn = sqlite3.connect("blog.db")
    post_id = conn.execute(
        "INSERT INTO posts (title, path, published_at) VALUES (?, ?, datetime('now')) RETURNING id",
        (title, post_path)
    ).fetchone()[0]
    
    for tag in tags:
        conn.execute("INSERT INTO post_tags (post_id, tag) VALUES (?, ?)", (post_id, tag))
    
    conn.commit()
    conn.close()
    
    # Update RSS feed
    update_rss_feed()
    
    # Send notifications
    notify_subscribers(title, post_path)
    
    return post_id

# If ANY step fails, ALL changes are automatically rolled back:
# - post file is deleted
# - database changes are reverted  
# - RSS feed is restored
# - notification emails are marked for cancellation (if possible)
```

### Example 2: E-commerce Order Processing

```python
@auto_transactional(
    name="order_processing",
    checkpoints=["payment_processed", "inventory_reserved"],
    retry_policy={"max_retries": 3, "backoff": "exponential"}
)
async def process_order(order_data):
    # Validate inventory
    for item in order_data['items']:
        if not check_inventory(item['sku'], item['quantity']):
            raise InsufficientInventoryError(item['sku'])
    
    # Process payment
    payment_result = await charge_credit_card(
        order_data['payment_info'], 
        order_data['total']
    )
    
    # Reserve inventory
    reservation_ids = []
    for item in order_data['items']:
        reservation_id = reserve_inventory(item['sku'], item['quantity'])
        reservation_ids.append(reservation_id)
    
    # Create order record
    conn = sqlite3.connect("orders.db")
    order_id = conn.execute(
        "INSERT INTO orders (customer_id, total, status) VALUES (?, ?, 'processing') RETURNING id",
        (order_data['customer_id'], order_data['total'])
    ).fetchone()[0]
    conn.commit()
    conn.close()
    
    # Send confirmation email
    await send_order_confirmation(order_data['customer_email'], order_id)
    
    return order_id

# Automatic rollback on failure:
# - Credit card charge is refunded
# - Inventory reservations are released
# - Order record is deleted
# - Confirmation email is not sent (or cancellation notice is sent)
```

### Example 3: Data Pipeline with Smart Proxies

```python
@workflow_aware
async def process_data_pipeline(input_file, output_dir, wtx):
    # Read and validate input
    data = wtx.file.read_json(input_file)
    
    # Process data in stages with checkpoints
    cleaned_data = clean_data(data)
    wtx.checkpoint("data_cleaned")
    
    # Transform data
    transformed_data = transform_data(cleaned_data)
    wtx.checkpoint("data_transformed")
    
    # Save intermediate results
    intermediate_file = f"{output_dir}/intermediate.json"
    await wtx.file.write_json(intermediate_file, transformed_data)
    
    # Upload to external service with compensation
    upload_result = await wtx.api.call(
        url="https://api.example.com/data",
        method="POST",
        json=transformed_data,
        compensation={
            "url": "https://api.example.com/data/{upload_id}",
            "method": "DELETE"
        }
    )
    
    # Update database
    await wtx.db.execute(
        "data.db",
        "INSERT INTO processed_files (input_file, output_dir, upload_id, processed_at) VALUES (?, ?, ?, datetime('now'))",
        (input_file, output_dir, upload_result['id'])
    )
    
    # Final output
    final_file = f"{output_dir}/final.json"
    await wtx.file.write_json(final_file, {"status": "completed", "upload_id": upload_result['id']})
    
    return upload_result['id']
```

## 🔄 Migration Path

### Phase 1: Drop-in Replacement (Week 1)
- Implement `@auto_transactional` decorator
- Basic operation detection for file and database operations
- Simple rollback mechanisms

### Phase 2: Enhanced Detection (Week 2)
- Add HTTP/API operation tracking
- Email operation tracking
- Process execution tracking
- Configuration options

### Phase 3: Smart Proxies (Week 3)
- Implement `@workflow_aware` decorator
- Smart proxy objects (`wtx.file.*`, `wtx.db.*`, etc.)
- Advanced compensation patterns

### Phase 4: Production Features (Week 4)
- Performance optimization
- Advanced error handling
- Monitoring and observability
- Documentation and examples

## 🎯 Benefits

1. **Zero Migration Cost**: Existing code works with just a decorator
2. **Progressive Enhancement**: Add features as needed
3. **Familiar Patterns**: Developers use existing knowledge
4. **Automatic Safety**: Transaction boundaries detected automatically
5. **Escape Hatches**: Full control available when needed
6. **Production Ready**: Handles real-world complexity

This design makes workflow transactions **accessible to every developer** while maintaining the power and flexibility of the full framework.