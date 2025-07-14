#!/usr/bin/env python3

"""
Workflow Parser

Analyzes user prompts to detect transaction boundaries and create workflow plans.
Uses pattern matching and NLP techniques to understand user intent.
"""

import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from workflow_tx_core import WorkflowPlan, Operation, OperationType


class IntentPattern(Enum):
    """Types of user intent patterns."""
    SINGLE_ATOMIC = "single_atomic"  # "Create X AND update Y AND notify Z"
    SEQUENTIAL = "sequential"        # "Create X. Then update Y. Later notify Z"
    CONDITIONAL = "conditional"      # "Create X. If successful, do Y"
    EXPLICIT_TX = "explicit_tx"      # "BEGIN TRANSACTION: ..."
    TEMPLATE = "template"            # "Deploy new version", "Setup blog"


@dataclass
class IntentSignal:
    """Represents a signal in the prompt indicating transaction intent."""
    pattern: IntentPattern
    confidence: float
    span: Tuple[int, int]  # Character positions in prompt
    data: Dict[str, Any]


class WorkflowParser:
    """
    Parses user prompts to detect workflow patterns and transaction boundaries.
    """
    
    def __init__(self):
        # Conjunction words that indicate atomic operations
        self.atomic_conjunctions = {
            'and', 'AND', '&', 'plus', '+', 'then also', 'and also',
            'along with', 'together with', 'as well as'
        }
        
        # Sequential indicators
        self.sequential_indicators = {
            'then', 'next', 'after that', 'afterwards', 'later',
            'subsequently', 'following that', 'once done'
        }
        
        # Conditional indicators  
        self.conditional_indicators = {
            'if', 'when', 'once', 'after', 'provided that',
            'assuming', 'in case', 'should'
        }
        
        # Explicit transaction markers
        self.transaction_markers = {
            'begin transaction', 'start transaction', 'begin tx',
            'commit transaction', 'commit tx', 'end transaction',
            'rollback transaction', 'rollback tx', 'abort transaction'
        }
        
        # Operation patterns
        self.operation_patterns = {
            OperationType.FILE_CREATE: [
                r'create\s+(?:a\s+)?(?:new\s+)?file',
                r'write\s+(?:a\s+)?(?:new\s+)?file',
                r'generate\s+(?:a\s+)?(?:new\s+)?file',
                r'make\s+(?:a\s+)?(?:new\s+)?file'
            ],
            OperationType.FILE_UPDATE: [
                r'update\s+(?:the\s+)?file',
                r'modify\s+(?:the\s+)?file',
                r'edit\s+(?:the\s+)?file',
                r'change\s+(?:the\s+)?file'
            ],
            OperationType.DB_INSERT: [
                r'add\s+(?:a\s+)?(?:new\s+)?record',
                r'insert\s+(?:a\s+)?(?:new\s+)?record',
                r'create\s+(?:a\s+)?(?:new\s+)?entry',
                r'save\s+(?:to\s+)?database'
            ],
            OperationType.API_CALL: [
                r'send\s+(?:a\s+)?notification',
                r'notify\s+(?:the\s+)?(?:users?|subscribers?)',
                r'call\s+(?:the\s+)?api',
                r'make\s+(?:an?\s+)?api\s+call'
            ]
        }
        
        # Workflow templates
        self.workflow_templates = {
            'blog_creation': {
                'patterns': [
                    r'create\s+(?:a\s+)?(?:new\s+)?blog\s+post',
                    r'publish\s+(?:a\s+)?(?:new\s+)?blog\s+post',
                    r'write\s+(?:a\s+)?(?:new\s+)?blog\s+(?:post|article)'
                ],
                'operations': [
                    'create_blog_file',
                    'update_index',
                    'update_metadata',
                    'notify_subscribers'
                ]
            },
            'deployment': {
                'patterns': [
                    r'deploy\s+(?:new\s+)?version',
                    r'release\s+(?:new\s+)?version',
                    r'push\s+(?:to\s+)?production'
                ],
                'operations': [
                    'update_code',
                    'migrate_database',
                    'restart_services',
                    'update_load_balancer'
                ]
            },
            'user_registration': {
                'patterns': [
                    r'register\s+(?:new\s+)?user',
                    r'create\s+(?:new\s+)?user\s+account',
                    r'sign\s+up\s+(?:new\s+)?user'
                ],
                'operations': [
                    'create_user_record',
                    'send_welcome_email',
                    'setup_user_profile',
                    'create_billing_record'
                ]
            }
        }
    
    def parse_prompt(self, prompt: str) -> WorkflowPlan:
        """Parse a user prompt into a workflow plan."""
        # Normalize prompt
        prompt = prompt.strip()
        
        # Detect intent patterns
        intent_signals = self._detect_intent_patterns(prompt)
        
        # Determine primary pattern
        primary_pattern = self._determine_primary_pattern(intent_signals)
        
        # Extract operations
        operations = self._extract_operations(prompt, primary_pattern)
        
        # Create workflow plan
        plan = WorkflowPlan(
            name=self._generate_workflow_name(prompt, primary_pattern),
            operations=operations,
            requires_confirmation=self._requires_confirmation(primary_pattern, operations),
            estimated_duration=self._estimate_duration(operations),
            risk_level=self._assess_risk_level(operations),
            description=self._generate_description(prompt, primary_pattern)
        )
        
        return plan
    
    def _detect_intent_patterns(self, prompt: str) -> List[IntentSignal]:
        """Detect various intent patterns in the prompt."""
        signals = []
        prompt_lower = prompt.lower()
        
        # Check for explicit transaction markers
        for marker in self.transaction_markers:
            if marker in prompt_lower:
                start = prompt_lower.find(marker)
                signals.append(IntentSignal(
                    pattern=IntentPattern.EXPLICIT_TX,
                    confidence=1.0,
                    span=(start, start + len(marker)),
                    data={"marker": marker}
                ))
        
        # Check for workflow templates
        for template_name, template_data in self.workflow_templates.items():
            for pattern in template_data['patterns']:
                if re.search(pattern, prompt_lower):
                    match = re.search(pattern, prompt_lower)
                    signals.append(IntentSignal(
                        pattern=IntentPattern.TEMPLATE,
                        confidence=0.9,
                        span=match.span(),
                        data={"template": template_name}
                    ))
        
        # Check for atomic conjunctions (AND operations)
        atomic_score = 0
        for conjunction in self.atomic_conjunctions:
            count = prompt_lower.count(conjunction.lower())
            atomic_score += count * 0.3
        
        if atomic_score > 0.5:
            signals.append(IntentSignal(
                pattern=IntentPattern.SINGLE_ATOMIC,
                confidence=min(atomic_score, 1.0),
                span=(0, len(prompt)),
                data={"conjunction_count": atomic_score / 0.3}
            ))
        
        # Check for sequential indicators
        sequential_score = 0
        for indicator in self.sequential_indicators:
            if indicator in prompt_lower:
                sequential_score += 0.4
        
        if sequential_score > 0:
            signals.append(IntentSignal(
                pattern=IntentPattern.SEQUENTIAL,
                confidence=min(sequential_score, 1.0),
                span=(0, len(prompt)),
                data={"indicator_count": sequential_score / 0.4}
            ))
        
        # Check for conditional indicators
        conditional_score = 0
        for indicator in self.conditional_indicators:
            if indicator in prompt_lower:
                conditional_score += 0.5
        
        if conditional_score > 0:
            signals.append(IntentSignal(
                pattern=IntentPattern.CONDITIONAL,
                confidence=min(conditional_score, 1.0),
                span=(0, len(prompt)),
                data={"conditional_words": conditional_score / 0.5}
            ))
        
        return signals
    
    def _determine_primary_pattern(self, signals: List[IntentSignal]) -> IntentPattern:
        """Determine the primary intent pattern from signals."""
        if not signals:
            return IntentPattern.SINGLE_ATOMIC  # Default
        
        # Sort by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)
        
        # Explicit transaction markers take precedence
        explicit_signals = [s for s in signals if s.pattern == IntentPattern.EXPLICIT_TX]
        if explicit_signals:
            return IntentPattern.EXPLICIT_TX
        
        # Templates have high priority
        template_signals = [s for s in signals if s.pattern == IntentPattern.TEMPLATE]
        if template_signals:
            return IntentPattern.TEMPLATE
        
        # Return highest confidence pattern
        return signals[0].pattern
    
    def _extract_operations(self, prompt: str, primary_pattern: IntentPattern) -> List[Operation]:
        """Extract operations from the prompt based on the primary pattern."""
        operations = []
        prompt_lower = prompt.lower()
        
        if primary_pattern == IntentPattern.TEMPLATE:
            # Use template-based operation extraction
            operations = self._extract_template_operations(prompt)
        else:
            # Use pattern-based operation extraction
            operations = self._extract_pattern_operations(prompt)
        
        # Add transaction ID to operation data
        tx_id = f"workflow_{hash(prompt) % 100000}"
        for op in operations:
            op.data['tx_id'] = tx_id
        
        return operations
    
    def _extract_template_operations(self, prompt: str) -> List[Operation]:
        """Extract operations using workflow templates."""
        operations = []
        prompt_lower = prompt.lower()
        
        # Find matching template
        for template_name, template_data in self.workflow_templates.items():
            for pattern in template_data['patterns']:
                if re.search(pattern, prompt_lower):
                    # Create operations from template
                    for i, op_name in enumerate(template_data['operations']):
                        operation = Operation(
                            id=f"{template_name}_{i}",
                            type=self._map_operation_name_to_type(op_name),
                            resource_type=self._get_resource_type_for_operation(op_name),
                            target=self._generate_target_for_operation(op_name, prompt),
                            data={"template_operation": op_name}
                        )
                        operations.append(operation)
                    break
        
        return operations
    
    def _extract_pattern_operations(self, prompt: str) -> List[Operation]:
        """Extract operations using pattern matching."""
        operations = []
        prompt_lower = prompt.lower()
        
        # Look for operation patterns
        for op_type, patterns in self.operation_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, prompt_lower)
                for match in matches:
                    # Extract target from context
                    target = self._extract_target_from_context(prompt, match, op_type)
                    
                    operation = Operation(
                        id=f"{op_type.value}_{len(operations)}",
                        type=op_type,
                        resource_type=self._get_resource_type_for_op_type(op_type),
                        target=target,
                        data={"extracted_from": match.group()}
                    )
                    operations.append(operation)
        
        return operations
    
    def _extract_target_from_context(self, prompt: str, match: re.Match, op_type: OperationType) -> str:
        """Extract operation target from surrounding context."""
        # Simple heuristic: look for words after the operation
        start = match.end()
        words = prompt[start:].split()[:5]  # Look at next 5 words
        
        # Filter out common stop words
        stop_words = {'the', 'a', 'an', 'to', 'for', 'with', 'in', 'on', 'at'}
        target_words = [w for w in words if w.lower() not in stop_words]
        
        if target_words:
            return ' '.join(target_words)
        else:
            # Default targets based on operation type
            if op_type == OperationType.FILE_CREATE:
                return "new_file.txt"
            elif op_type == OperationType.DB_INSERT:
                return "records"
            elif op_type == OperationType.API_CALL:
                return "external_service"
            else:
                return "target"
    
    def _map_operation_name_to_type(self, op_name: str) -> OperationType:
        """Map template operation name to operation type."""
        mapping = {
            'create_blog_file': OperationType.FILE_CREATE,
            'update_index': OperationType.FILE_UPDATE,
            'update_metadata': OperationType.DB_UPDATE,
            'notify_subscribers': OperationType.API_CALL,
            'update_code': OperationType.FILE_UPDATE,
            'migrate_database': OperationType.DB_UPDATE,
            'restart_services': OperationType.API_CALL,
            'update_load_balancer': OperationType.API_CALL,
            'create_user_record': OperationType.DB_INSERT,
            'send_welcome_email': OperationType.API_CALL,
            'setup_user_profile': OperationType.FILE_CREATE,
            'create_billing_record': OperationType.DB_INSERT
        }
        return mapping.get(op_name, OperationType.CUSTOM)
    
    def _get_resource_type_for_operation(self, op_name: str) -> str:
        """Get resource type for template operation."""
        if 'file' in op_name or 'index' in op_name or 'profile' in op_name:
            return 'filesystem'
        elif 'database' in op_name or 'record' in op_name or 'metadata' in op_name:
            return 'database'
        elif 'notify' in op_name or 'email' in op_name or 'api' in op_name or 'service' in op_name:
            return 'api'
        else:
            return 'custom'
    
    def _get_resource_type_for_op_type(self, op_type: OperationType) -> str:
        """Get resource type for operation type."""
        if op_type in [OperationType.FILE_CREATE, OperationType.FILE_UPDATE, OperationType.FILE_DELETE]:
            return 'filesystem'
        elif op_type in [OperationType.DB_INSERT, OperationType.DB_UPDATE, OperationType.DB_DELETE]:
            return 'database'
        elif op_type == OperationType.API_CALL:
            return 'api'
        else:
            return 'custom'
    
    def _generate_target_for_operation(self, op_name: str, prompt: str) -> str:
        """Generate target for template operation."""
        # Extract relevant parts from prompt
        if 'blog' in op_name:
            # Look for blog post title or filename
            if 'about' in prompt:
                topic = prompt.split('about')[-1].strip().split('.')[0]
                return f"posts/{topic.replace(' ', '-').lower()}.md"
            else:
                return "posts/new-post.md"
        elif 'user' in op_name:
            return "users"
        elif 'email' in op_name:
            return "email_service"
        else:
            return op_name.replace('_', '-')
    
    def _generate_workflow_name(self, prompt: str, pattern: IntentPattern) -> str:
        """Generate a name for the workflow."""
        # Extract key words from prompt
        words = prompt.lower().split()
        key_words = []
        
        for word in words:
            if len(word) > 3 and word.isalpha():
                key_words.append(word)
            if len(key_words) >= 3:
                break
        
        if key_words:
            return '_'.join(key_words)
        else:
            return f"{pattern.value}_workflow"
    
    def _requires_confirmation(self, pattern: IntentPattern, operations: List[Operation]) -> bool:
        """Determine if workflow requires user confirmation."""
        # High-risk operations require confirmation
        high_risk_types = {OperationType.FILE_DELETE, OperationType.DB_DELETE}
        
        if any(op.type in high_risk_types for op in operations):
            return True
        
        # Complex workflows require confirmation
        if len(operations) > 5:
            return True
        
        # API calls with external services
        api_operations = [op for op in operations if op.type == OperationType.API_CALL]
        if len(api_operations) > 2:
            return True
        
        return False
    
    def _estimate_duration(self, operations: List[Operation]) -> float:
        """Estimate workflow duration in seconds."""
        # Simple heuristic based on operation types
        duration_map = {
            OperationType.FILE_CREATE: 1.0,
            OperationType.FILE_UPDATE: 0.5,
            OperationType.FILE_DELETE: 0.2,
            OperationType.DB_INSERT: 2.0,
            OperationType.DB_UPDATE: 1.5,
            OperationType.DB_DELETE: 1.0,
            OperationType.API_CALL: 3.0,
            OperationType.CUSTOM: 2.0
        }
        
        total_duration = sum(duration_map.get(op.type, 2.0) for op in operations)
        return total_duration
    
    def _assess_risk_level(self, operations: List[Operation]) -> str:
        """Assess risk level of the workflow."""
        high_risk_types = {OperationType.FILE_DELETE, OperationType.DB_DELETE}
        medium_risk_types = {OperationType.DB_UPDATE, OperationType.API_CALL}
        
        if any(op.type in high_risk_types for op in operations):
            return "high"
        elif any(op.type in medium_risk_types for op in operations) or len(operations) > 3:
            return "medium"
        else:
            return "low"
    
    def _generate_description(self, prompt: str, pattern: IntentPattern) -> str:
        """Generate a description for the workflow."""
        return f"Workflow generated from: '{prompt[:100]}...' using {pattern.value} pattern"


# Export the parser
__all__ = ['WorkflowParser', 'IntentPattern', 'IntentSignal']