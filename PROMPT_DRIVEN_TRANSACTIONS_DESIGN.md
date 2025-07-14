# Prompt-Driven Transaction Boundaries Design

## 🎯 Vision Statement

**Enable users to express complex multi-step workflows in natural language and have the system automatically determine transaction boundaries, coordinate resources, and execute operations atomically.**

```
User: "Create a blog post about AI safety AND update the main index AND notify all subscribers"
System: ✅ Detected single atomic workflow with 3 operations
        🔄 Executing with cross-resource transaction coordination
        📝 Created: posts/ai-safety-blog-post.md
        🔄 Updated: index.html  
        📧 Notified: 1,247 subscribers
        ✅ All operations completed atomically
```

## 🧠 Core Challenge

Transform natural language prompts into executable workflows with **intelligent transaction boundary detection**:

```
Input:  "Create X AND update Y AND notify Z"
Output: SingleWorkflow[CreateOp, UpdateOp, NotifyOp] → Atomic execution

Input:  "Create X. Then later update Y. Finally notify Z."  
Output: ThreeWorkflows[CreateOp][UpdateOp][NotifyOp] → Sequential execution

Input:  "Create user account. If successful, send welcome email and setup billing"
Output: ConditionalWorkflow[CreateOp → IF(success) → [EmailOp, BillingOp]]
```

## 🏗️ Architecture Overview

```
Natural Language Prompt
         ↓
   Intent Parser (LLM)
         ↓
   Boundary Detector
         ↓
   Operation Extractor
         ↓
   Resource Coordinator
         ↓
   Workflow Executor
         ↓
   Atomic Execution
```

### Key Components

1. **Prompt Analysis Engine**: Understands user intent and workflow structure
2. **Boundary Detection AI**: Determines transaction scope from linguistic cues
3. **Operation Mapper**: Converts natural language to executable operations
4. **Resource Orchestrator**: Auto-configures required resource managers
5. **Workflow Compiler**: Generates optimized execution plans
6. **Atomic Executor**: Ensures ACID properties across all operations

## 📋 Boundary Detection Patterns

### Pattern 1: Conjunction-Based Atomicity

**Linguistic Cues**: "AND", "and", "plus", "also", "along with"

```python
# Input Examples:
"Create blog post AND update RSS feed AND notify subscribers"
"Upload file AND update database AND send confirmation email"
"Process payment AND reserve inventory AND create shipment"

# System Interpretation:
TransactionBoundary.ATOMIC → All operations succeed or all rollback
```

### Pattern 2: Sequential Workflow Boundaries

**Linguistic Cues**: ". Then", ". Next", ". After that", ". Later"

```python
# Input Examples:
"Create user account. Then send welcome email. Later setup billing."
"Process order. Next update inventory. Finally generate receipt."

# System Interpretation:
TransactionBoundary.SEQUENTIAL → Separate transactions with dependencies
```

### Pattern 3: Conditional Transaction Nesting

**Linguistic Cues**: "If successful", "Upon completion", "When done"

```python
# Input Examples:
"Create user account. If successful, send welcome email and setup billing"
"Process payment. Upon completion, reserve inventory and ship items"

# System Interpretation:
TransactionBoundary.CONDITIONAL → Nested transactions with success conditions
```

### Pattern 4: Explicit Boundary Control

**Linguistic Cues**: "BEGIN TRANSACTION", "atomically", "all-or-nothing"

```python
# Input Examples:
"BEGIN TRANSACTION: Create post, update index, notify users"
"Atomically: process payment, update inventory, create order"

# System Interpretation:
TransactionBoundary.EXPLICIT → User-defined atomic scope
```

### Pattern 5: Rollback and Recovery Patterns

**Linguistic Cues**: "rollback if", "undo on failure", "compensate"

```python
# Input Examples:
"Create order AND reserve inventory. Rollback if payment fails"
"Upload files AND update database. Undo everything on any failure"

# System Interpretation:
TransactionBoundary.ATOMIC_WITH_CONDITIONS → Enhanced rollback logic
```

## 🤖 AI-Powered Intent Analysis

### LLM Integration for Prompt Understanding

```python
class PromptAnalysisEngine:
    """Uses LLM to understand user intent and extract workflow structure."""
    
    def __init__(self, llm_client):
        self.llm = llm_client
        self.prompt_template = self._load_analysis_prompt()
    
    async def analyze_prompt(self, user_prompt: str) -> PromptAnalysis:
        """Analyze user prompt to extract workflow intent."""
        
        analysis_prompt = f"""
        Analyze this user prompt for workflow transaction boundaries:
        
        USER PROMPT: "{user_prompt}"
        
        Determine:
        1. TRANSACTION_SCOPE: [atomic, sequential, conditional, mixed]
        2. OPERATIONS: List of discrete operations to perform
        3. RESOURCES: Types of resources involved (file, database, api, email, etc.)
        4. DEPENDENCIES: Operation dependencies and order
        5. ROLLBACK_STRATEGY: How to handle failures
        6. CONFIDENCE: How certain are you about this analysis (0-1)
        
        Response format: JSON
        """
        
        response = await self.llm.complete(analysis_prompt)
        return PromptAnalysis.from_json(response)


class PromptAnalysis:
    """Structured analysis of user prompt."""
    
    transaction_scope: TransactionScope  # atomic, sequential, conditional
    operations: List[OperationIntent]     # What to do
    resources: List[ResourceType]         # What resources needed
    dependencies: Dict[str, List[str]]    # Operation order/deps
    rollback_strategy: RollbackStrategy   # How to handle failures
    confidence: float                     # Certainty score
```

### Example Analysis Results

```python
# Prompt: "Create blog post AND update index AND notify subscribers"
PromptAnalysis(
    transaction_scope=TransactionScope.ATOMIC,
    operations=[
        OperationIntent(
            type="file_create",
            description="Create blog post file",
            target_pattern="posts/{title}.md",
            confidence=0.95
        ),
        OperationIntent(
            type="file_update", 
            description="Update site index",
            target_pattern="index.html",
            confidence=0.90
        ),
        OperationIntent(
            type="email_send",
            description="Notify subscribers",
            target_pattern="subscribers@{domain}",
            confidence=0.85
        )
    ],
    resources=[ResourceType.FILESYSTEM, ResourceType.EMAIL],
    dependencies={"notify_subscribers": ["create_blog_post", "update_index"]},
    rollback_strategy=RollbackStrategy.FULL_ROLLBACK,
    confidence=0.92
)
```

## 🔧 Operation Extraction and Mapping

### Intent-to-Operation Compiler

```python
class OperationCompiler:
    """Converts natural language intents to executable operations."""
    
    def __init__(self):
        self.operation_templates = self._load_operation_templates()
        self.parameter_extractor = ParameterExtractor()
    
    def compile_operations(self, analysis: PromptAnalysis, context: Dict) -> List[Operation]:
        """Convert operation intents to executable Operation objects."""
        
        operations = []
        for intent in analysis.operations:
            # Match intent to operation template
            template = self._match_template(intent)
            
            # Extract parameters from context
            params = self.parameter_extractor.extract(intent, context)
            
            # Generate Operation object
            operation = template.instantiate(
                id=f"{intent.type}_{uuid.uuid4().hex[:8]}",
                target=self._resolve_target(intent.target_pattern, params),
                data=self._prepare_operation_data(params)
            )
            
            operations.append(operation)
        
        return operations


class OperationTemplate:
    """Template for generating operations from intents."""
    
    def __init__(self, intent_type: str, operation_type: OperationType, 
                 resource_type: str, parameter_schema: Dict):
        self.intent_type = intent_type
        self.operation_type = operation_type
        self.resource_type = resource_type
        self.parameter_schema = parameter_schema
    
    def instantiate(self, **kwargs) -> Operation:
        """Create Operation instance from template."""
        return Operation(
            type=self.operation_type,
            resource_type=self.resource_type,
            **kwargs
        )


# Built-in operation templates
OPERATION_TEMPLATES = {
    "file_create": OperationTemplate(
        intent_type="file_create",
        operation_type=OperationType.FILE_CREATE,
        resource_type="filesystem",
        parameter_schema={"target": str, "content": str}
    ),
    "blog_post_create": OperationTemplate(
        intent_type="blog_post_create", 
        operation_type=OperationType.FILE_CREATE,
        resource_type="filesystem",
        parameter_schema={"title": str, "content": str, "tags": List[str]}
    ),
    "database_insert": OperationTemplate(
        intent_type="database_insert",
        operation_type=OperationType.DB_INSERT,
        resource_type="database", 
        parameter_schema={"table": str, "data": Dict}
    ),
    "email_notify": OperationTemplate(
        intent_type="email_notify",
        operation_type=OperationType.EMAIL_SEND,
        resource_type="email",
        parameter_schema={"recipients": List[str], "subject": str, "body": str}
    )
}
```

### Parameter Extraction from Context

```python
class ParameterExtractor:
    """Extracts operation parameters from user prompt and context."""
    
    def extract(self, intent: OperationIntent, context: Dict) -> Dict:
        """Extract parameters needed for operation."""
        
        if intent.type == "blog_post_create":
            return {
                "title": self._extract_title(intent.description, context),
                "content": context.get("blog_content", ""),
                "tags": self._extract_tags(intent.description, context),
                "author": context.get("current_user", "unknown")
            }
        
        elif intent.type == "email_notify":
            return {
                "recipients": self._get_subscriber_list(context),
                "subject": self._generate_subject(intent, context),
                "body": self._generate_email_body(intent, context)
            }
        
        # ... more extractors
    
    def _extract_title(self, description: str, context: Dict) -> str:
        """Extract title from natural language description."""
        # Use regex, NLP, or LLM to extract title
        # e.g., "Create blog post about AI safety" → "AI Safety"
        pass
    
    def _extract_tags(self, description: str, context: Dict) -> List[str]:
        """Extract relevant tags from description."""
        # Use keyword extraction, topic modeling, or LLM
        pass
```

## 🎭 Workflow Orchestration Engine

### Boundary-Aware Workflow Compiler

```python
class WorkflowCompiler:
    """Compiles analyzed prompts into executable workflows with proper boundaries."""
    
    def compile_prompt(self, user_prompt: str, context: Dict = None) -> WorkflowExecutionPlan:
        """Convert user prompt to executable workflow plan."""
        
        # 1. Analyze prompt intent
        analysis = await self.prompt_analyzer.analyze_prompt(user_prompt)
        
        # 2. Validate confidence threshold
        if analysis.confidence < self.min_confidence_threshold:
            return self._request_clarification(analysis, user_prompt)
        
        # 3. Compile operations
        operations = self.operation_compiler.compile_operations(analysis, context or {})
        
        # 4. Create workflow(s) based on boundary analysis
        workflows = self._create_workflows_from_boundaries(analysis, operations)
        
        # 5. Set up resource coordination
        resource_plan = self._plan_resource_coordination(workflows, analysis.resources)
        
        # 6. Generate execution plan
        return WorkflowExecutionPlan(
            workflows=workflows,
            resource_plan=resource_plan,
            rollback_strategy=analysis.rollback_strategy,
            original_prompt=user_prompt,
            confidence=analysis.confidence
        )
    
    def _create_workflows_from_boundaries(self, analysis: PromptAnalysis, 
                                        operations: List[Operation]) -> List[WorkflowTransaction]:
        """Create workflow transactions based on detected boundaries."""
        
        if analysis.transaction_scope == TransactionScope.ATOMIC:
            # Single workflow with all operations
            wtx = WorkflowTransaction("atomic_workflow", f"Atomic: {analysis.description}")
            for operation in operations:
                wtx.add_operation(operation)
            return [wtx]
        
        elif analysis.transaction_scope == TransactionScope.SEQUENTIAL:
            # Multiple workflows with dependencies
            workflows = []
            for i, operation in enumerate(operations):
                wtx = WorkflowTransaction(f"sequential_step_{i}", f"Step {i+1}")
                wtx.add_operation(operation)
                workflows.append(wtx)
            return workflows
        
        elif analysis.transaction_scope == TransactionScope.CONDITIONAL:
            # Nested workflows with conditions
            return self._create_conditional_workflows(analysis, operations)
    
    def _create_conditional_workflows(self, analysis: PromptAnalysis, 
                                    operations: List[Operation]) -> List[ConditionalWorkflow]:
        """Create conditional workflow structures."""
        
        # Parse conditional structure from dependencies
        primary_ops = [op for op in operations if not analysis.dependencies.get(op.id)]
        conditional_ops = [op for op in operations if analysis.dependencies.get(op.id)]
        
        # Create primary workflow
        primary_workflow = WorkflowTransaction("primary", "Primary operations")
        for op in primary_ops:
            primary_workflow.add_operation(op)
        
        # Create conditional workflows
        conditional_workflows = []
        for op in conditional_ops:
            conditional_wf = ConditionalWorkflow(
                condition=lambda: primary_workflow.status == WorkflowStatus.COMPLETED,
                workflow=WorkflowTransaction(f"conditional_{op.id}", f"Conditional: {op.target}")
            )
            conditional_wf.workflow.add_operation(op)
            conditional_workflows.append(conditional_wf)
        
        return [primary_workflow] + conditional_workflows


class ConditionalWorkflow:
    """Workflow that executes only if condition is met."""
    
    def __init__(self, condition: Callable[[], bool], workflow: WorkflowTransaction):
        self.condition = condition
        self.workflow = workflow
    
    async def execute_if_condition_met(self):
        """Execute workflow only if condition is satisfied."""
        if self.condition():
            await self.workflow.execute()
        else:
            self.workflow.status = WorkflowStatus.SKIPPED
```

## 🚀 Automatic Resource Coordination

### Smart Resource Manager Selection

```python
class ResourceOrchestrator:
    """Automatically configures and coordinates resource managers."""
    
    def __init__(self):
        self.available_managers = {
            ResourceType.FILESYSTEM: FileSystemManager,
            ResourceType.DATABASE: DatabaseManager,
            ResourceType.EMAIL: EmailManager,
            ResourceType.HTTP_API: APIManager,
            ResourceType.CLOUD_STORAGE: CloudStorageManager,
            ResourceType.MESSAGE_QUEUE: MessageQueueManager
        }
    
    def setup_resources_for_workflow(self, workflow: WorkflowTransaction, 
                                   required_resources: List[ResourceType],
                                   context: Dict) -> None:
        """Auto-configure resource managers for workflow."""
        
        for resource_type in required_resources:
            manager_class = self.available_managers.get(resource_type)
            if not manager_class:
                raise ValueError(f"No manager available for {resource_type}")
            
            # Auto-configure manager with intelligent defaults
            manager = self._auto_configure_manager(manager_class, context)
            workflow.register_resource_manager(resource_type.value, manager)
    
    def _auto_configure_manager(self, manager_class, context: Dict):
        """Automatically configure resource manager with context-aware defaults."""
        
        if manager_class == DatabaseManager:
            # Auto-detect database from context or use default
            db_path = context.get("database_path", "default.db")
            return DatabaseManager(db_path)
        
        elif manager_class == EmailManager:
            # Auto-configure email settings from context
            return EmailManager(
                smtp_host=context.get("smtp_host", "localhost"),
                smtp_port=context.get("smtp_port", 587),
                from_address=context.get("from_email", "noreply@example.com")
            )
        
        elif manager_class == FileSystemManager:
            # Configure with workspace context
            workspace = context.get("workspace_dir", os.getcwd())
            return FileSystemManager(base_directory=workspace)
        
        # ... more auto-configuration logic


class IntelligentResourceDetector:
    """Detects required resources from operation analysis."""
    
    def detect_resources(self, operations: List[Operation]) -> List[ResourceType]:
        """Detect all resource types needed for operations."""
        
        resources = set()
        
        for operation in operations:
            if operation.type in [OperationType.FILE_CREATE, OperationType.FILE_UPDATE, OperationType.FILE_DELETE]:
                resources.add(ResourceType.FILESYSTEM)
            
            elif operation.type in [OperationType.DB_INSERT, OperationType.DB_UPDATE, OperationType.DB_DELETE]:
                resources.add(ResourceType.DATABASE)
            
            elif operation.type == OperationType.EMAIL_SEND:
                resources.add(ResourceType.EMAIL)
            
            elif operation.type == OperationType.API_CALL:
                resources.add(ResourceType.HTTP_API)
            
            # Add cloud storage detection
            if self._involves_cloud_storage(operation):
                resources.add(ResourceType.CLOUD_STORAGE)
        
        return list(resources)
    
    def _involves_cloud_storage(self, operation: Operation) -> bool:
        """Detect if operation involves cloud storage."""
        target = operation.target.lower()
        return any(cloud in target for cloud in ['s3://', 'gs://', 'azure://', 'blob://'])
```

## 💬 User Experience and Interaction

### Conversational Workflow Management

```python
class ConversationalWorkflowManager:
    """Manages workflow execution with natural language interaction."""
    
    async def handle_user_prompt(self, prompt: str, user_context: Dict) -> WorkflowResponse:
        """Process user prompt and execute workflow with feedback."""
        
        # 1. Compile prompt to execution plan
        execution_plan = await self.workflow_compiler.compile_prompt(prompt, user_context)
        
        # 2. Check confidence and request clarification if needed
        if execution_plan.confidence < 0.8:
            return self._request_clarification(execution_plan, prompt)
        
        # 3. Show execution plan to user for confirmation
        if execution_plan.requires_confirmation:
            return self._request_confirmation(execution_plan)
        
        # 4. Execute workflow with real-time feedback
        return await self._execute_with_feedback(execution_plan)
    
    def _request_clarification(self, plan: WorkflowExecutionPlan, original_prompt: str) -> WorkflowResponse:
        """Request clarification when prompt analysis confidence is low."""
        
        ambiguities = []
        
        if plan.confidence < 0.6:
            ambiguities.append("I'm not sure I understand what you want to do.")
        
        if len(plan.workflows) > 1 and plan.boundary_confidence < 0.7:
            ambiguities.append("I'm unclear whether these should be separate steps or one atomic operation.")
        
        if plan.missing_parameters:
            ambiguities.append(f"I need more information about: {', '.join(plan.missing_parameters)}")
        
        clarification_prompt = f"""
        I understood your request as: {plan.interpretation}
        
        However, I need clarification on:
        {chr(10).join(f'• {amb}' for amb in ambiguities)}
        
        Could you provide more details or rephrase your request?
        """
        
        return WorkflowResponse(
            status="clarification_needed",
            message=clarification_prompt,
            suggested_prompts=plan.suggested_alternatives
        )
    
    def _request_confirmation(self, plan: WorkflowExecutionPlan) -> WorkflowResponse:
        """Request user confirmation for high-impact operations."""
        
        confirmation_message = f"""
        I'm about to execute the following workflow:
        
        🎯 Goal: {plan.description}
        📋 Operations:
        {chr(10).join(f'  {i+1}. {op.description}' for i, op in enumerate(plan.operations))}
        
        🔄 Transaction Scope: {plan.transaction_scope.value}
        📁 Resources: {', '.join(r.value for r in plan.required_resources)}
        
        This will {'modify' if plan.has_side_effects else 'read'} the following:
        {chr(10).join(f'  • {target}' for target in plan.affected_targets)}
        
        Proceed? (yes/no)
        """
        
        return WorkflowResponse(
            status="confirmation_required",
            message=confirmation_message,
            execution_plan=plan
        )
    
    async def _execute_with_feedback(self, plan: WorkflowExecutionPlan) -> WorkflowResponse:
        """Execute workflow with real-time progress feedback."""
        
        try:
            # Start execution with progress tracking
            progress_tracker = WorkflowProgressTracker()
            
            for i, workflow in enumerate(plan.workflows):
                # Update progress
                progress_tracker.start_workflow(i, len(plan.workflows), workflow.description)
                
                # Execute workflow
                await workflow.execute()
                
                # Report completion
                progress_tracker.complete_workflow(i, workflow.get_summary())
            
            return WorkflowResponse(
                status="completed",
                message="✅ All operations completed successfully!",
                results=progress_tracker.get_final_summary(),
                execution_time=progress_tracker.total_time
            )
            
        except WorkflowError as e:
            return WorkflowResponse(
                status="failed",
                message=f"❌ Workflow failed: {e.user_friendly_message()}",
                error=e,
                rollback_summary=e.rollback_summary
            )


class WorkflowProgressTracker:
    """Tracks and reports workflow execution progress."""
    
    def __init__(self):
        self.start_time = time.time()
        self.workflow_progress = []
        self.current_workflow = None
    
    def start_workflow(self, index: int, total: int, description: str):
        """Report workflow start."""
        self.current_workflow = {
            'index': index,
            'total': total,
            'description': description,
            'start_time': time.time(),
            'operations': []
        }
        
        print(f"🔄 [{index+1}/{total}] Starting: {description}")
    
    def complete_workflow(self, index: int, summary: Dict):
        """Report workflow completion."""
        duration = time.time() - self.current_workflow['start_time']
        print(f"✅ [{index+1}/{self.current_workflow['total']}] Completed in {duration:.2f}s")
        
        self.workflow_progress.append({
            **self.current_workflow,
            'duration': duration,
            'summary': summary
        })
```

## 🧪 Example End-to-End Flow

### Complete Prompt-to-Execution Pipeline

```python
# User Input
user_prompt = "Create a blog post about AI safety AND update the main index AND notify all subscribers"

# Step 1: Prompt Analysis
analysis = await prompt_analyzer.analyze_prompt(user_prompt)
# Result: TransactionScope.ATOMIC with 3 operations

# Step 2: Operation Compilation  
operations = operation_compiler.compile_operations(analysis, {
    "blog_title": "AI Safety in Modern Systems",
    "blog_content": "AI safety is crucial for...",
    "author": "Dr. Sarah Chen",
    "subscriber_list": ["user1@example.com", "user2@example.com"]
})

# Step 3: Workflow Creation
workflow = WorkflowTransaction("blog_publishing_atomic", "Atomic blog publishing workflow")
for operation in operations:
    workflow.add_operation(operation)

# Step 4: Resource Auto-Configuration
resource_orchestrator.setup_resources_for_workflow(
    workflow, 
    [ResourceType.FILESYSTEM, ResourceType.EMAIL], 
    context={"workspace_dir": "/blog", "smtp_host": "mail.example.com"}
)

# Step 5: Atomic Execution
try:
    results = await workflow.execute()
    print("✅ Blog post published atomically!")
    print(f"📝 Created: {results[0]}")  # posts/ai-safety-in-modern-systems.md
    print(f"🔄 Updated: {results[1]}")  # index.html
    print(f"📧 Notified: {results[2]}")  # 2 subscribers
    
except WorkflowError as e:
    print("❌ Publishing failed - all changes rolled back")
    print(f"Failed at: {e.step_name}")
    print(f"Completed: {e.completed_steps}")
```

## 🎯 Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)
- [ ] `PromptAnalysisEngine` with LLM integration
- [ ] Basic boundary detection patterns (AND, THEN)
- [ ] `OperationCompiler` with core templates
- [ ] `ResourceOrchestrator` for auto-configuration

### Phase 2: Advanced Analysis (Week 3-4)
- [ ] Conditional workflow support (IF/WHEN patterns)
- [ ] Parameter extraction and context integration
- [ ] Confidence scoring and clarification requests
- [ ] Enhanced operation templates library

### Phase 3: User Experience (Week 5-6)
- [ ] Conversational workflow management
- [ ] Real-time progress tracking and feedback
- [ ] Interactive confirmation and clarification
- [ ] Error recovery and retry mechanisms

### Phase 4: Production Features (Week 7-8)
- [ ] Performance optimization and caching
- [ ] Advanced rollback and compensation
- [ ] Monitoring and observability
- [ ] Security and permission management

## 🎖️ Success Metrics

### User Experience
- **Prompt Understanding**: > 90% accuracy for common patterns
- **Boundary Detection**: > 95% accuracy for explicit patterns (AND/THEN)
- **Parameter Extraction**: > 85% success rate with context
- **User Satisfaction**: Natural conversation flow

### System Performance
- **Analysis Latency**: < 2 seconds for prompt analysis
- **Execution Coordination**: < 100ms overhead for resource setup
- **Error Recovery**: Clear, actionable error messages
- **Scalability**: Support for 10+ concurrent workflows

### Business Impact
- **Adoption Rate**: Non-technical users can create workflows
- **Development Velocity**: 50x faster workflow creation
- **Error Reduction**: Fewer transaction boundary mistakes
- **User Retention**: Natural language reduces learning curve

---

**This design enables true prompt-driven workflows where users express intent in natural language and the system automatically handles all technical complexity of transaction coordination, resource management, and atomic execution.**