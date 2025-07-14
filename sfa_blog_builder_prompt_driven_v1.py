#!/usr/bin/env python3

# /// script
# dependencies = [
#   "anthropic>=0.45.2",
#   "rich>=13.7.0",
# ]
# ///

"""
/// Example Usage

# Simple single operations
uv run sfa_blog_builder_prompt_driven_v1.py --prompt "Create a blog post about Python async programming"
uv run sfa_blog_builder_prompt_driven_v1.py --prompt "List all blog posts"

# Multi-step ATOMIC operations (our new capability!)
uv run sfa_blog_builder_prompt_driven_v1.py --prompt "Create a blog post about Claude AND update the site index AND show all posts"
uv run sfa_blog_builder_prompt_driven_v1.py --prompt "Create a blog post about AI safety AND list all posts"

# Multi-step SEQUENTIAL operations
uv run sfa_blog_builder_prompt_driven_v1.py --prompt "Create a blog post about Python. Then list all posts. Finally show the latest post"

# Demo mode
uv run sfa_blog_builder_prompt_driven_v1.py --demo

///
"""

import os
import sys
import argparse
import sqlite3
import asyncio
import re
import uuid
from pathlib import Path
from typing import Dict, Any, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from anthropic import Anthropic
from enum import Enum
from dataclasses import dataclass

# Import our transaction framework
from tx_mini import Transaction, Op, tx_op
from adaptors import FileSystemAdaptor, SQLiteAdaptor

console = Console()

# Initialize adaptors
BLOG_DIR = Path("blog_posts")
BLOG_DB = "blog.db"

# Create necessary directories
BLOG_DIR.mkdir(exist_ok=True)

# Initialize adaptors
fs_adaptor = FileSystemAdaptor()
db_adaptor = SQLiteAdaptor(BLOG_DB)

def init_database():
    """Initialize the blog database."""
    
    conn = sqlite3.connect(BLOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# PROMPT-DRIVEN TRANSACTION BOUNDARY DETECTION
# ============================================

class TransactionScope(Enum):
    """Types of transaction boundaries."""
    ATOMIC = "atomic"           # Single transaction for all operations
    SEQUENTIAL = "sequential"   # Separate transactions with dependencies
    CONDITIONAL = "conditional" # Nested transactions with conditions


@dataclass
class OperationIntent:
    """Represents an intended operation extracted from natural language."""
    type: str                   # operation type (create_post, list_posts, etc.)
    description: str           # natural language description
    parameters: Dict[str, Any] # extracted parameters
    confidence: float          # confidence in this interpretation


@dataclass
class WorkflowPlan:
    """Result of analyzing a user prompt."""
    transaction_scope: TransactionScope
    operations: List[OperationIntent]
    confidence: float
    description: str


class PromptAnalyzer:
    """Analyzes natural language prompts to determine workflow structure."""
    
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
            r'\.\s*Finally\b'
        ]
        
        # Operation patterns
        self.operation_patterns = {
            'create_post': [
                r'create\s+(?:a\s+)?(?:blog\s+)?post',
                r'write\s+(?:a\s+)?(?:blog\s+)?post',
                r'make\s+(?:a\s+)?(?:blog\s+)?post'
            ],
            'list_posts': [
                r'list\s+(?:all\s+)?(?:blog\s+)?posts',
                r'show\s+(?:all\s+)?(?:blog\s+)?posts',
                r'display\s+(?:all\s+)?(?:blog\s+)?posts'
            ],
            'update_index': [
                r'update\s+(?:the\s+)?(?:site\s+)?index',
                r'refresh\s+(?:the\s+)?(?:site\s+)?index',
                r'regenerate\s+(?:the\s+)?(?:site\s+)?index'
            ],
            'delete_post': [
                r'delete\s+(?:the\s+)?(?:blog\s+)?post',
                r'remove\s+(?:the\s+)?(?:blog\s+)?post'
            ]
        }
    
    def analyze_prompt(self, prompt: str) -> WorkflowPlan:
        """Analyze user prompt to determine workflow structure."""
        
        # Detect transaction boundaries
        transaction_scope = self._detect_boundaries(prompt)
        
        # Extract operations
        operations = self._extract_operations(prompt)
        
        # Calculate confidence
        confidence = self._calculate_confidence(operations, transaction_scope)
        
        return WorkflowPlan(
            transaction_scope=transaction_scope,
            operations=operations,
            confidence=confidence,
            description=f"{transaction_scope.value} workflow with {len(operations)} operations"
        )
    
    def _detect_boundaries(self, prompt: str) -> TransactionScope:
        """Detect transaction scope from prompt text."""
        
        # Check for explicit atomic indicators
        if any(re.search(pattern, prompt, re.IGNORECASE) for pattern in self.atomic_patterns):
            return TransactionScope.ATOMIC
        
        # Check for sequential patterns
        if any(re.search(pattern, prompt, re.IGNORECASE) for pattern in self.sequential_patterns):
            return TransactionScope.SEQUENTIAL
        
        # Default to atomic for single-sentence prompts
        if '.' not in prompt.strip():
            return TransactionScope.ATOMIC
        
        # Multiple sentences without clear indicators = sequential
        return TransactionScope.SEQUENTIAL
    
    def _extract_operations(self, prompt: str) -> List[OperationIntent]:
        """Extract operation intents from prompt."""
        
        operations = []
        
        # Split by common separators while preserving the delimiters
        segments = re.split(r'(\s+AND\s+|\s+and\s+|\.\s*Then\s+|\.\s*Next\s+|\.\s*Finally\s+)', prompt, flags=re.IGNORECASE)
        
        # Filter out separators and empty segments
        segments = [seg.strip() for seg in segments if seg.strip() and not re.match(r'^\s*(AND|and|Then|Next|Finally)\s*$', seg.strip(), re.IGNORECASE)]
        
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
                            parameters=self._extract_parameters(op_type, segment),
                            confidence=0.9  # High confidence for pattern matches
                        )
                        operations.append(intent)
                        break  # Found match, move to next segment
                else:
                    continue  # Continue to next pattern
                break  # Found match, move to next segment
        
        return operations
    
    def _extract_parameters(self, op_type: str, segment: str) -> Dict[str, Any]:
        """Extract parameters from operation segment."""
        
        params = {}
        
        if op_type == 'create_post':
            # Extract topic for blog posts
            about_match = re.search(r'about\s+([^.]+)', segment, re.IGNORECASE)
            if about_match:
                topic = about_match.group(1).strip()
                # Clean up topic (remove trailing words like "AND")
                topic = re.sub(r'\s+(AND|and)\s*$', '', topic).strip()
                params['topic'] = topic
                params['slug'] = topic.lower().replace(' ', '-').replace("'", "")
                params['title'] = f"Understanding {topic.title()}"
        
        return params
    
    def _calculate_confidence(self, operations: List[OperationIntent], 
                            transaction_scope: TransactionScope) -> float:
        """Calculate confidence in the analysis."""
        
        if not operations:
            return 0.0
        
        # Average operation confidence
        op_confidence = sum(op.confidence for op in operations) / len(operations)
        
        # Boost confidence for clear patterns
        if transaction_scope in [TransactionScope.ATOMIC, TransactionScope.SEQUENTIAL]:
            op_confidence += 0.05
        
        return min(1.0, op_confidence)


# ENHANCED BLOG BUILDER WITH PROMPT-DRIVEN BOUNDARIES
# ===================================================

class EnhancedBlogBuilderAgent:
    """Blog builder agent with prompt-driven transaction boundaries."""
    
    def __init__(self, api_key: str = None):
        self.client = Anthropic(api_key=api_key) if api_key else None
        self.prompt_analyzer = PromptAnalyzer()
    
    async def process_prompt(self, prompt: str) -> None:
        """Process a user prompt with automatic transaction boundary detection."""
        
        console.print(f"\n[cyan]🧠 Analyzing prompt:[/cyan] {prompt}")
        
        # Analyze the prompt
        plan = self.prompt_analyzer.analyze_prompt(prompt)
        
        console.print(f"[yellow]📊 Detected:[/yellow] {plan.transaction_scope.value.upper()} workflow")
        console.print(f"[yellow]🎯 Operations:[/yellow] {len(plan.operations)}")
        console.print(f"[yellow]🎯 Confidence:[/yellow] {plan.confidence:.2f}")
        
        # Show detected operations
        for i, op in enumerate(plan.operations, 1):
            console.print(f"  {i}. {op.type} - {op.description}")
        
        if plan.confidence < 0.7:
            console.print("[red]⚠️  Low confidence in prompt analysis. Proceeding with best interpretation.[/red]")
        
        # Execute based on transaction scope
        if plan.transaction_scope == TransactionScope.ATOMIC:
            await self._execute_atomic_workflow(plan)
        elif plan.transaction_scope == TransactionScope.SEQUENTIAL:
            await self._execute_sequential_workflow(plan)
        else:
            console.print("[yellow]Conditional workflows not yet implemented. Falling back to atomic.[/yellow]")
            await self._execute_atomic_workflow(plan)
    
    async def _execute_atomic_workflow(self, plan: WorkflowPlan) -> None:
        """Execute all operations in a single atomic transaction."""
        
        console.print(f"\n[green]🔄 Executing ATOMIC workflow with {len(plan.operations)} operations...[/green]")
        
        # Create one transaction for all operations
        async with Transaction("atomic_workflow") as tx:
            results = []
            
            for op in plan.operations:
                if op.type == "create_post":
                    result = await self._add_create_post_to_transaction(tx, op)
                    results.append(f"Created post: {result}")
                
                elif op.type == "update_index":
                    result = await self._add_update_index_to_transaction(tx, op)
                    results.append(f"Updated index: {result}")
                
                elif op.type == "list_posts":
                    # For atomic execution, we'll show posts after the transaction completes
                    results.append("Posts will be listed after atomic completion")
                
                elif op.type == "delete_post":
                    result = await self._add_delete_post_to_transaction(tx, op)
                    results.append(f"Deleted post: {result}")
        
        # Transaction completed atomically
        console.print("[green]✅ ATOMIC transaction completed successfully![/green]")
        
        # Now handle any list operations (which don't need transactions)
        for op in plan.operations:
            if op.type == "list_posts":
                console.print("\n[cyan]📋 Current blog posts:[/cyan]")
                posts = self.list_posts()
                self.display_posts(posts)
        
        # Show summary
        console.print(f"\n[green]🎉 Atomic workflow completed:[/green]")
        for result in results:
            console.print(f"  ✓ {result}")
    
    async def _execute_sequential_workflow(self, plan: WorkflowPlan) -> None:
        """Execute operations in separate sequential transactions."""
        
        console.print(f"\n[blue]🔄 Executing SEQUENTIAL workflow with {len(plan.operations)} operations...[/blue]")
        
        for i, op in enumerate(plan.operations, 1):
            console.print(f"\n[blue]Step {i}/{len(plan.operations)}:[/blue] {op.description}")
            
            if op.type == "create_post":
                await self._execute_create_post(op)
                console.print("[green]✓ Post created[/green]")
            
            elif op.type == "update_index":
                await self._execute_update_index(op)
                console.print("[green]✓ Index updated[/green]")
            
            elif op.type == "list_posts":
                console.print("[cyan]📋 Listing posts:[/cyan]")
                posts = self.list_posts()
                self.display_posts(posts)
            
            elif op.type == "delete_post":
                await self._execute_delete_post(op)
                console.print("[green]✓ Post deleted[/green]")
        
        console.print(f"\n[green]🎉 Sequential workflow completed![/green]")
    
    async def _add_create_post_to_transaction(self, tx: Transaction, op: OperationIntent) -> str:
        """Add create post operations to an existing transaction."""
        
        # Extract parameters
        topic = op.parameters.get('topic', 'Sample Topic')
        slug = op.parameters.get('slug', 'sample-topic')
        title = op.parameters.get('title', f"About {topic}")
        
        # Generate content
        content = f"""# {title}

This is a blog post about {topic}. Here's an overview of the key concepts:

## Introduction

{topic} is an important topic that deserves detailed explanation.

## Key Points

- Understanding the basics
- Practical applications  
- Best practices
- Common pitfalls to avoid

## Conclusion

{topic} offers many opportunities for learning and application.

---
*Generated automatically by the blog builder agent*
"""
        
        # Register file operation
        file_op = Op("fs.write", {
            "path": f"blog_posts/{slug}.md", 
            "data": content
        })
        tx.register(file_op, fs_adaptor)
        
        # Register database operation
        db_op = Op("db.exec", {
            "sql": "INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
            "params": (slug, title, content)
        })
        tx.register(db_op, db_adaptor)
        
        return f"{slug}.md"
    
    async def _add_update_index_to_transaction(self, tx: Transaction, op: OperationIntent) -> str:
        """Add update index operation to an existing transaction."""
        
        # Generate simple index content
        index_content = """# Blog Index

This is the main index page for the blog.

## Latest Posts

Check the database for the most recent posts.

---
*Last updated by the blog builder agent*
"""
        
        # Register index file operation
        index_op = Op("fs.write", {
            "path": "index.html", 
            "data": index_content
        })
        tx.register(index_op, fs_adaptor)
        
        return "index.html"
    
    async def _add_delete_post_to_transaction(self, tx: Transaction, op: OperationIntent) -> str:
        """Add delete post operations to an existing transaction."""
        
        # For demo, delete a specific post (would need better parameter extraction)
        slug = op.parameters.get('slug', 'sample-post')
        
        # Register file deletion
        file_op = Op("fs.delete", {
            "path": f"blog_posts/{slug}.md"
        })
        tx.register(file_op, fs_adaptor)
        
        # Register database deletion
        db_op = Op("db.exec", {
            "sql": "DELETE FROM posts WHERE slug = ?",
            "params": (slug,)
        })
        tx.register(db_op, db_adaptor)
        
        return f"{slug}.md"
    
    async def _execute_create_post(self, op: OperationIntent) -> None:
        """Execute create post in its own transaction."""
        async with Transaction(f"create_post_{op.parameters.get('slug', 'post')}") as tx:
            await self._add_create_post_to_transaction(tx, op)
    
    async def _execute_update_index(self, op: OperationIntent) -> None:
        """Execute update index in its own transaction."""
        async with Transaction("update_index") as tx:
            await self._add_update_index_to_transaction(tx, op)
    
    async def _execute_delete_post(self, op: OperationIntent) -> None:
        """Execute delete post in its own transaction."""
        async with Transaction(f"delete_post_{op.parameters.get('slug', 'post')}") as tx:
            await self._add_delete_post_to_transaction(tx, op)
    
    def list_posts(self) -> list:
        """List all blog posts."""
        conn = sqlite3.connect(BLOG_DB)
        cursor = conn.execute("SELECT slug, title, created_at FROM posts ORDER BY created_at DESC")
        posts = cursor.fetchall()
        conn.close()
        return posts
    
    def display_posts(self, posts: list) -> None:
        """Display posts in a formatted table."""
        if not posts:
            console.print("[yellow]No blog posts found.[/yellow]")
            return
        
        table = Table(title="Blog Posts", title_style="bold magenta")
        table.add_column("Slug", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Created", style="yellow")
        
        for slug, title, created_at in posts:
            table.add_row(slug, title, created_at)
        
        console.print(table)


# DEMO FUNCTIONALITY (preserved from original)
# ============================================

async def run_demo():
    """Run demonstration of atomic transactions."""
    console.print(Panel("Running Enhanced Blog Builder Demo with Prompt-Driven Boundaries", style="bold green"))
    
    agent = EnhancedBlogBuilderAgent()
    
    # Demo 1: Test atomic boundary detection
    console.print("\n[yellow]Demo 1: Testing ATOMIC boundary detection...[/yellow]")
    await agent.process_prompt("Create a blog post about Machine Learning AND update the site index AND show all posts")
    
    # Demo 2: Test sequential boundary detection  
    console.print("\n[yellow]Demo 2: Testing SEQUENTIAL boundary detection...[/yellow]")
    await agent.process_prompt("Create a blog post about AI Ethics. Then list all posts. Finally update the index.")
    
    # Demo 3: Test simple single operation
    console.print("\n[yellow]Demo 3: Testing simple single operation...[/yellow]")
    await agent.process_prompt("List all blog posts")


# MAIN FUNCTION
# =============

async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Enhanced Blog Builder Agent with Prompt-Driven Transactions")
    parser.add_argument("--prompt", help="What do you want to do with the blog?")
    parser.add_argument("--demo", action="store_true", help="Run demo scenarios")
    
    args = parser.parse_args()
    
    if not args.demo and not args.prompt:
        parser.error("Either --prompt or --demo is required")
    
    # Initialize database
    init_database()
    
    if args.demo:
        await run_demo()
        return
    
    # Check for API key (optional for this demo)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[yellow]Note: ANTHROPIC_API_KEY not set. Using pattern-based analysis only.[/yellow]")
    
    # Process user request with prompt-driven analysis
    agent = EnhancedBlogBuilderAgent(api_key)
    await agent.process_prompt(args.prompt)


if __name__ == "__main__":
    asyncio.run(main())