#!/usr/bin/env python3

"""
Prompt-Driven Transaction Boundaries - Prototype Implementation

Demonstrates how natural language prompts can be analyzed to automatically
determine transaction boundaries and execute workflows atomically.
"""

import re
import uuid
import asyncio
from enum import Enum
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass
import json

# Import existing workflow framework
from workflow_tx_core import WorkflowTransaction, Operation, OperationType
from workflow_resource_managers import FileSystemManager, DatabaseManager


class TransactionScope(Enum):
    """Types of transaction boundaries."""
    ATOMIC = "atomic"           # Single transaction for all operations
    SEQUENTIAL = "sequential"   # Separate transactions with dependencies
    CONDITIONAL = "conditional" # Nested transactions with conditions
    MIXED = "mixed"            # Complex mixed patterns


@dataclass
class OperationIntent:
    """Represents an intended operation extracted from natural language."""
    type: str                   # operation type (file_create, db_insert, etc.)
    description: str           # natural language description
    target_pattern: str        # target pattern with placeholders
    parameters: Dict[str, Any] # extracted parameters
    confidence: float          # confidence in this interpretation


@dataclass
class PromptAnalysis:
    """Result of analyzing a user prompt."""
    transaction_scope: TransactionScope
    operations: List[OperationIntent]
    resources: List[str]
    dependencies: Dict[str, List[str]]
    confidence: float
    description: str


class PromptBoundaryDetector:
    """Detects transaction boundaries from natural language patterns."""
    
    def __init__(self):
        # Patterns for detecting atomic operations
        self.atomic_patterns = [
            r'\bAND\b',
            r'\band\b',
            r'\bplus\b',
            r'\balso\b',
            r'\balong with\b',
            r'\btogether with\b'
        ]
        
        # Patterns for detecting sequential operations
        self.sequential_patterns = [
            r'\.\s*Then\b',
            r'\.\s*Next\b',
            r'\.\s*After that\b',
            r'\.\s*Later\b',
            r'\.\s*Subsequently\b'
        ]
        
        # Patterns for detecting conditional operations
        self.conditional_patterns = [
            r'\bIf successful\b',
            r'\bUpon completion\b',
            r'\bWhen done\b',
            r'\bAfter completing\b',
            r'\bif.*succeeds?\b'
        ]
    
    def detect_boundaries(self, prompt: str) -> TransactionScope:
        """Detect transaction scope from prompt text."""
        
        # Check for explicit atomic indicators
        if any(re.search(pattern, prompt, re.IGNORECASE) for pattern in self.atomic_patterns):
            return TransactionScope.ATOMIC
        
        # Check for conditional patterns
        if any(re.search(pattern, prompt, re.IGNORECASE) for pattern in self.conditional_patterns):
            return TransactionScope.CONDITIONAL
        
        # Check for sequential patterns
        if any(re.search(pattern, prompt, re.IGNORECASE) for pattern in self.sequential_patterns):
            return TransactionScope.SEQUENTIAL
        
        # Default to atomic for single-sentence prompts
        if '.' not in prompt.strip():
            return TransactionScope.ATOMIC
        
        # Multiple sentences without clear indicators = sequential
        return TransactionScope.SEQUENTIAL


class OperationExtractor:
    """Extracts operation intents from natural language."""
    
    def __init__(self):
        # Operation pattern templates
        self.operation_patterns = {
            'file_create': [
                r'create\s+(?:a\s+)?(?:blog\s+)?post',
                r'write\s+(?:a\s+)?file',
                r'generate\s+(?:a\s+)?document',
                r'make\s+(?:a\s+)?file'
            ],
            'file_update': [
                r'update\s+(?:the\s+)?(?:main\s+)?index',
                r'modify\s+(?:the\s+)?(?:main\s+)?page',
                r'change\s+(?:the\s+)?file',
                r'edit\s+(?:the\s+)?document'
            ],
            'email_send': [
                r'notify\s+(?:all\s+)?subscribers',
                r'send\s+(?:notification\s+)?emails?',
                r'email\s+(?:the\s+)?users',
                r'alert\s+(?:the\s+)?subscribers'
            ],
            'db_insert': [
                r'add\s+(?:to\s+)?(?:the\s+)?database',
                r'insert\s+(?:into\s+)?(?:the\s+)?(?:database|db)',
                r'store\s+(?:in\s+)?(?:the\s+)?(?:database|db)',
                r'save\s+(?:to\s+)?(?:the\s+)?(?:database|db)'
            ],
            'user_create': [
                r'create\s+(?:a\s+)?(?:new\s+)?user\s+account',
                r'register\s+(?:a\s+)?(?:new\s+)?user',
                r'add\s+(?:a\s+)?(?:new\s+)?user'
            ],
            'order_process': [
                r'process\s+(?:the\s+)?order',
                r'handle\s+(?:the\s+)?order',
                r'fulfill\s+(?:the\s+)?order'
            ],
            'payment_process': [
                r'process\s+(?:the\s+)?payment',
                r'charge\s+(?:the\s+)?(?:credit\s+)?card',
                r'handle\s+(?:the\s+)?payment'
            ]
        }
    
    def extract_operations(self, prompt: str) -> List[OperationIntent]:
        """Extract operation intents from prompt."""
        
        operations = []
        
        # Split by common separators
        segments = re.split(r'\s+AND\s+|\s+and\s+|\.\s*Then\s+|\.\s*Next\s+', prompt, flags=re.IGNORECASE)
        
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            
            # Try to match each operation type
            for op_type, patterns in self.operation_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, segment, re.IGNORECASE):
                        intent = OperationIntent(
                            type=op_type,
                            description=segment,
                            target_pattern=self._extract_target_pattern(op_type, segment),
                            parameters=self._extract_parameters(op_type, segment),
                            confidence=0.8  # Simple confidence scoring
                        )
                        operations.append(intent)
                        break  # Found match, move to next segment
                else:
                    continue  # Continue to next pattern
                break  # Found match, move to next segment
        
        return operations
    
    def _extract_target_pattern(self, op_type: str, segment: str) -> str:
        """Extract target pattern based on operation type."""
        
        if op_type == 'file_create':
            # Look for "about X" or specific topics
            about_match = re.search(r'about\s+([^.]+)', segment, re.IGNORECASE)
            if about_match:
                topic = about_match.group(1).strip()
                return f"posts/{topic.lower().replace(' ', '-')}.md"
            return "posts/{title}.md"
        
        elif op_type == 'file_update':
            if 'index' in segment.lower():
                return "index.html"
            return "{filename}"
        
        elif op_type == 'email_send':
            return "subscribers@{domain}"
        
        elif op_type == 'db_insert':
            return "{table}"
        
        return "{target}"
    
    def _extract_parameters(self, op_type: str, segment: str) -> Dict[str, Any]:
        """Extract parameters from operation segment."""
        
        params = {}
        
        if op_type == 'file_create':
            # Extract topic for blog posts
            about_match = re.search(r'about\s+([^.]+)', segment, re.IGNORECASE)
            if about_match:
                topic = about_match.group(1).strip()
                params['title'] = topic.title()
                params['content'] = f"This is a blog post about {topic}."
        
        elif op_type == 'email_send':
            # Extract recipient information
            if 'subscribers' in segment.lower():
                params['recipients'] = 'all_subscribers'
                params['subject'] = 'New Update'
        
        return params


class SimplePromptAnalyzer:
    """Simple prompt analyzer for demonstration purposes."""
    
    def __init__(self):
        self.boundary_detector = PromptBoundaryDetector()
        self.operation_extractor = OperationExtractor()
    
    def analyze_prompt(self, prompt: str) -> PromptAnalysis:
        """Analyze user prompt to determine workflow structure."""
        
        # Detect transaction boundaries
        transaction_scope = self.boundary_detector.detect_boundaries(prompt)
        
        # Extract operations
        operations = self.operation_extractor.extract_operations(prompt)
        
        # Determine required resources
        resources = self._determine_resources(operations)
        
        # Simple dependency analysis
        dependencies = self._analyze_dependencies(operations, transaction_scope)
        
        # Calculate confidence
        confidence = self._calculate_confidence(operations, transaction_scope)
        
        return PromptAnalysis(
            transaction_scope=transaction_scope,
            operations=operations,
            resources=resources,
            dependencies=dependencies,
            confidence=confidence,
            description=f"Workflow with {len(operations)} operations"
        )
    
    def _determine_resources(self, operations: List[OperationIntent]) -> List[str]:
        """Determine required resource types from operations."""
        
        resource_mapping = {
            'file_create': 'filesystem',
            'file_update': 'filesystem',
            'email_send': 'email',
            'db_insert': 'database',
            'user_create': 'database',
            'order_process': 'database',
            'payment_process': 'api'
        }
        
        resources = set()
        for operation in operations:
            if operation.type in resource_mapping:
                resources.add(resource_mapping[operation.type])
        
        return list(resources)
    
    def _analyze_dependencies(self, operations: List[OperationIntent], 
                            transaction_scope: TransactionScope) -> Dict[str, List[str]]:
        """Analyze operation dependencies."""
        
        if transaction_scope == TransactionScope.ATOMIC:
            # No dependencies for atomic operations
            return {}
        
        # Simple sequential dependencies
        dependencies = {}
        for i, operation in enumerate(operations):
            if i > 0:
                dependencies[operation.type] = [operations[i-1].type]
        
        return dependencies
    
    def _calculate_confidence(self, operations: List[OperationIntent], 
                            transaction_scope: TransactionScope) -> float:
        """Calculate confidence in the analysis."""
        
        if not operations:
            return 0.0
        
        # Average operation confidence
        op_confidence = sum(op.confidence for op in operations) / len(operations)
        
        # Boost confidence for clear patterns
        if transaction_scope in [TransactionScope.ATOMIC, TransactionScope.SEQUENTIAL]:
            op_confidence += 0.1
        
        return min(1.0, op_confidence)


class PromptWorkflowCompiler:
    """Compiles analyzed prompts into executable workflows."""
    
    def __init__(self):
        self.prompt_analyzer = SimplePromptAnalyzer()
    
    async def compile_prompt_to_workflow(self, prompt: str, context: Dict = None) -> List[WorkflowTransaction]:
        """Compile user prompt into executable workflow(s)."""
        
        # Analyze prompt
        analysis = self.prompt_analyzer.analyze_prompt(prompt)
        
        print(f"📊 Analysis: {analysis.transaction_scope.value} workflow with {len(analysis.operations)} operations")
        print(f"🎯 Confidence: {analysis.confidence:.2f}")
        
        # Convert to operations
        operations = self._compile_operations(analysis.operations, context or {})
        
        # Create workflows based on transaction scope
        workflows = self._create_workflows(analysis, operations)
        
        # Setup resource managers
        for workflow in workflows:
            self._setup_resource_managers(workflow, analysis.resources)
        
        return workflows
    
    def _compile_operations(self, intents: List[OperationIntent], context: Dict) -> List[Operation]:
        """Convert operation intents to executable operations."""
        
        operations = []
        
        for intent in intents:
            # Generate operation based on type
            if intent.type == 'file_create':
                operation = Operation(
                    id=f"file_create_{uuid.uuid4().hex[:8]}",
                    type=OperationType.FILE_CREATE,
                    resource_type="filesystem",
                    target=intent.target_pattern.format(**intent.parameters, **context),
                    data={
                        "tx_id": context.get("tx_id", "unknown"),
                        "content": intent.parameters.get("content", f"# {intent.parameters.get('title', 'New Post')}\n\nContent goes here...")
                    }
                )
            
            elif intent.type == 'file_update':
                operation = Operation(
                    id=f"file_update_{uuid.uuid4().hex[:8]}",
                    type=OperationType.FILE_UPDATE,
                    resource_type="filesystem",
                    target=intent.target_pattern,
                    data={
                        "tx_id": context.get("tx_id", "unknown"),
                        "content": f"<html><body><h1>Updated Index</h1><p>Last updated: now</p></body></html>"
                    }
                )
            
            elif intent.type == 'email_send':
                operation = Operation(
                    id=f"email_send_{uuid.uuid4().hex[:8]}",
                    type=OperationType.EMAIL_SEND,
                    resource_type="email",
                    target="subscribers@example.com",
                    data={
                        "tx_id": context.get("tx_id", "unknown"),
                        "subject": intent.parameters.get("subject", "New Update"),
                        "body": f"A new update is available!"
                    }
                )
            
            elif intent.type == 'db_insert':
                operation = Operation(
                    id=f"db_insert_{uuid.uuid4().hex[:8]}",
                    type=OperationType.DB_INSERT,
                    resource_type="database",
                    target="posts",
                    data={
                        "tx_id": context.get("tx_id", "unknown"),
                        "record_data": {
                            "title": intent.parameters.get("title", "New Post"),
                            "created_at": "now"
                        }
                    }
                )
            
            else:
                # Generic operation
                operation = Operation(
                    id=f"{intent.type}_{uuid.uuid4().hex[:8]}",
                    type=OperationType.CUSTOM,
                    resource_type="custom",
                    target=intent.target_pattern,
                    data={"tx_id": context.get("tx_id", "unknown"), **intent.parameters}
                )
            
            operations.append(operation)
        
        return operations
    
    def _create_workflows(self, analysis: PromptAnalysis, operations: List[Operation]) -> List[WorkflowTransaction]:
        """Create workflows based on transaction scope."""
        
        if analysis.transaction_scope == TransactionScope.ATOMIC:
            # Single atomic workflow
            workflow = WorkflowTransaction("atomic_prompt_workflow", f"Atomic: {analysis.description}")
            
            for operation in operations:
                operation.data["tx_id"] = workflow.id
                workflow.add_operation(operation)
            
            return [workflow]
        
        elif analysis.transaction_scope == TransactionScope.SEQUENTIAL:
            # Multiple sequential workflows
            workflows = []
            
            for i, operation in enumerate(operations):
                workflow = WorkflowTransaction(f"sequential_step_{i}", f"Step {i+1}: {operation.target}")
                operation.data["tx_id"] = workflow.id
                workflow.add_operation(operation)
                workflows.append(workflow)
            
            return workflows
        
        else:
            # Default to atomic for now
            return self._create_workflows(
                PromptAnalysis(
                    transaction_scope=TransactionScope.ATOMIC,
                    operations=analysis.operations,
                    resources=analysis.resources,
                    dependencies=analysis.dependencies,
                    confidence=analysis.confidence,
                    description=analysis.description
                ),
                operations
            )
    
    def _setup_resource_managers(self, workflow: WorkflowTransaction, required_resources: List[str]):
        """Setup resource managers for workflow."""
        
        if "filesystem" in required_resources:
            workflow.register_resource_manager("filesystem", FileSystemManager())
        
        if "database" in required_resources:
            workflow.register_resource_manager("database", DatabaseManager(":memory:"))
        
        # Note: Email and API managers would need to be implemented
        # For demo purposes, we'll skip them
        print(f"📁 Configured resources: {required_resources}")


# Demo and Testing Functions
async def demo_prompt_driven_workflow():
    """Demonstrate prompt-driven workflow execution."""
    
    print("🚀 PROMPT-DRIVEN WORKFLOW DEMONSTRATION")
    print("=" * 60)
    
    compiler = PromptWorkflowCompiler()
    
    # Test cases
    test_prompts = [
        "Create a blog post about AI safety AND update the main index AND notify all subscribers",
        "Create user account. Then send welcome email. Later setup billing.",
        "Process payment. If successful, reserve inventory and ship items",
        "Write a file called test.txt and also update the database"
    ]
    
    for i, prompt in enumerate(test_prompts, 1):
        print(f"\n🧪 TEST {i}: {prompt}")
        print("-" * 60)
        
        try:
            # Compile prompt to workflows
            workflows = await compiler.compile_prompt_to_workflow(
                prompt, 
                context={"title": "AI Safety", "domain": "example.com"}
            )
            
            print(f"📋 Generated {len(workflows)} workflow(s)")
            
            # Execute workflows
            for j, workflow in enumerate(workflows):
                print(f"\n🔄 Executing workflow {j+1}: {workflow.name}")
                
                try:
                    results = await workflow.execute()
                    print(f"✅ Workflow {j+1} completed successfully")
                    print(f"📊 Results: {len(results)} operations executed")
                    
                except Exception as e:
                    print(f"❌ Workflow {j+1} failed: {e}")
                    print("🔄 Automatic rollback performed")
            
        except Exception as e:
            print(f"❌ Failed to process prompt: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 Demonstration completed!")
    print("💡 This shows how natural language can drive automatic workflow boundaries")


if __name__ == "__main__":
    asyncio.run(demo_prompt_driven_workflow())