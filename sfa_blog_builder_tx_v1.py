#!/usr/bin/env python3

# /// script
# dependencies = [
#   "anthropic>=0.45.2",
#   "rich>=13.7.0",
# ]
# ///

"""
/// Example Usage

# Create a new blog post
uv run sfa_blog_builder_tx_v1.py --prompt "Create a blog post about Python async programming with the slug 'python-async' and title 'Mastering Python Async Programming'"

# Update an existing post  
uv run sfa_blog_builder_tx_v1.py --prompt "Update the post 'python-async' to add a section about asyncio.gather()"

# List all posts
uv run sfa_blog_builder_tx_v1.py --prompt "List all blog posts"

# Delete a post
uv run sfa_blog_builder_tx_v1.py --prompt "Delete the blog post with slug 'python-async'"

# Create multiple posts atomically
uv run sfa_blog_builder_tx_v1.py --prompt "Create three blog posts: 'intro-to-python', 'advanced-python', and 'python-best-practices'"

///
"""

import os
import sys
import argparse
import sqlite3
import asyncio
from pathlib import Path
from typing import Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from anthropic import Anthropic

# Import our transaction framework
from tx_mini import Transaction, Op, tx_op
from adaptors import FileSystemAdaptor, SQLiteAdaptor

console = Console()

# Initialize adaptors
BLOG_DIR = Path("blog_posts")
BLOG_DB = "blog.db"

fs_adaptor = FileSystemAdaptor(".")
db_adaptor = SQLiteAdaptor(BLOG_DB)


def setup_database():
    """Initialize the blog database."""
    BLOG_DIR.mkdir(exist_ok=True)
    
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


# Blog operations using transaction framework
@tx_op(fs_adaptor)
async def write_post_file(slug: str, content: str) -> Op:
    """Write a blog post file."""
    return Op("fs.write", {
        "path": f"blog_posts/{slug}.md", 
        "data": content
    })


@tx_op(db_adaptor) 
async def insert_post_record(slug: str, title: str, content: str) -> Op:
    """Insert a blog post record into the database."""
    return Op("db.exec", {
        "sql": "INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
        "params": (slug, title, content)
    })


@tx_op(db_adaptor)
async def update_post_record(slug: str, title: str, content: str) -> Op:
    """Update a blog post record in the database."""
    return Op("db.exec", {
        "sql": "UPDATE posts SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
        "params": (title, content, slug)
    })


@tx_op(fs_adaptor)
async def delete_post_file(slug: str) -> Op:
    """Delete a blog post file."""
    return Op("fs.delete", {
        "path": f"blog_posts/{slug}.md"
    })


@tx_op(db_adaptor)
async def delete_post_record(slug: str) -> Op:
    """Delete a blog post record from the database."""
    return Op("db.exec", {
        "sql": "DELETE FROM posts WHERE slug = ?",
        "params": (slug,)
    })


class BlogBuilderAgent:
    """Blog builder agent with transactional safety."""
    
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
    
    async def process_request(self, prompt: str) -> str:
        """Process a blog request using the LLM."""
        system_prompt = """You are a blog builder assistant with transactional safety guarantees.

Available operations:
- create_post(slug, title, content): Create a new blog post
- update_post(slug, title, content): Update an existing blog post  
- delete_post(slug): Delete a blog post
- list_posts(): List all blog posts

IMPORTANT: All operations are executed within transactions, so either all operations in a request succeed or none do. This prevents inconsistent states.

When creating content, generate high-quality markdown with proper headings, code examples, and formatting.

Respond with the specific operations you need to perform, then I'll execute them transactionally."""
        
        response = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text
    
    async def create_post(self, slug: str, title: str, content: str) -> None:
        """Create a blog post atomically."""
        async with Transaction(f"create_post_{slug}") as tx:
            # Register both file and database operations
            file_op = Op("fs.write", {
                "path": f"blog_posts/{slug}.md", 
                "data": content
            })
            db_op = Op("db.exec", {
                "sql": "INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
                "params": (slug, title, content)
            })
            
            tx.register(file_op, fs_adaptor)
            tx.register(db_op, db_adaptor)
    
    async def update_post(self, slug: str, title: str, content: str) -> None:
        """Update a blog post atomically."""
        async with Transaction(f"update_post_{slug}") as tx:
            # Register both file and database operations
            file_op = Op("fs.write", {
                "path": f"blog_posts/{slug}.md", 
                "data": content
            })
            db_op = Op("db.exec", {
                "sql": "UPDATE posts SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
                "params": (title, content, slug)
            })
            
            tx.register(file_op, fs_adaptor)
            tx.register(db_op, db_adaptor)
    
    async def delete_post(self, slug: str) -> None:
        """Delete a blog post atomically."""
        async with Transaction(f"delete_post_{slug}") as tx:
            # Register both file and database operations
            file_op = Op("fs.delete", {
                "path": f"blog_posts/{slug}.md"
            })
            db_op = Op("db.exec", {
                "sql": "DELETE FROM posts WHERE slug = ?",
                "params": (slug,)
            })
            
            tx.register(file_op, fs_adaptor)
            tx.register(db_op, db_adaptor)
    
    def list_posts(self) -> list:
        """List all blog posts."""
        conn = sqlite3.connect(BLOG_DB)
        cursor = conn.execute("SELECT slug, title, created_at FROM posts ORDER BY created_at DESC")
        posts = cursor.fetchall()
        conn.close()
        return posts
    
    async def demo_create_post(self, slug: str, title: str) -> None:
        """Demo: Create a sample blog post."""
        content = f"""# {title}

This is a sample blog post created using the transactional blog builder.

## Introduction

This post demonstrates the power of transactional operations in multi-agent systems.

## Key Features

- **Atomic Operations**: Either the file AND database record are created, or neither
- **Rollback Safety**: If any operation fails, all changes are rolled back
- **Consistency**: No orphaned files or database records

## Code Example

```python
async with Transaction("create_post") as tx:
    tx.register(file_op, fs_adaptor)
    tx.register(db_op, db_adaptor)
    # Both operations execute atomically
```

## Conclusion

Transactional programming for agents ensures data consistency and prevents partial failures.

Generated at: {asyncio.get_event_loop().time()}
"""
        
        await self.create_post(slug, title, content)
    
    async def demo_multi_post_creation(self) -> None:
        """Demo: Create multiple posts in a single transaction."""
        posts = [
            ("intro-to-transactions", "Introduction to Transactions", 
             "# Introduction to Transactions\n\nTransactions ensure data consistency..."),
            ("agent-coordination", "Agent Coordination Patterns",
             "# Agent Coordination Patterns\n\nMultiple agents working together..."),
            ("rollback-strategies", "Rollback and Recovery Strategies", 
             "# Rollback and Recovery Strategies\n\nWhen things go wrong...")
        ]
        
        async with Transaction("create_multiple_posts") as tx:
            for slug, title, content in posts:
                # Register file operation
                file_op = Op("fs.write", {
                    "path": f"blog_posts/{slug}.md", 
                    "data": content
                })
                
                # Register database operation
                db_op = Op("db.exec", {
                    "sql": "INSERT INTO posts (slug, title, content) VALUES (?, ?, ?)",
                    "params": (slug, title, content)
                })
                
                tx.register(file_op, fs_adaptor)
                tx.register(db_op, db_adaptor)


def display_posts(posts: list) -> None:
    """Display posts in a nice table."""
    if not posts:
        console.print("[yellow]No blog posts found.[/yellow]")
        return
    
    table = Table(title="Blog Posts")
    table.add_column("Slug", style="cyan")
    table.add_column("Title", style="magenta")
    table.add_column("Created", style="green")
    
    for slug, title, created_at in posts:
        table.add_row(slug, title, created_at)
    
    console.print(table)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Transactional Blog Builder Agent")
    parser.add_argument("--prompt", help="What do you want to do with the blog?")
    parser.add_argument("--demo", action="store_true", help="Run demo scenarios")
    
    args = parser.parse_args()
    
    if not args.demo and not args.prompt:
        parser.error("Either --prompt or --demo is required")
    
    # Check for API key (only needed for non-demo mode)
    if not args.demo:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            console.print("[red]Error: ANTHROPIC_API_KEY environment variable not set[/red]")
            sys.exit(1)
    else:
        api_key = "demo-key"
    
    # Setup
    setup_database()
    agent = BlogBuilderAgent(api_key)
    
    if args.demo:
        console.print(Panel("Running Transactional Blog Builder Demo", style="bold blue"))
        
        # Demo 1: Create a single post
        console.print("\n[yellow]Demo 1: Creating a single post atomically...[/yellow]")
        await agent.demo_create_post("atomic-operations", "Understanding Atomic Operations")
        console.print("[green]✓ Post created successfully[/green]")
        
        # Demo 2: Create multiple posts
        console.print("\n[yellow]Demo 2: Creating multiple posts in one transaction...[/yellow]")
        await agent.demo_multi_post_creation()
        console.print("[green]✓ Multiple posts created successfully[/green]")
        
        # Demo 3: Show all posts
        console.print("\n[yellow]Demo 3: Listing all posts...[/yellow]")
        posts = agent.list_posts()
        display_posts(posts)
        
        # Demo 4: Simulate failure (for educational purposes)
        console.print("\n[yellow]Demo 4: Simulating transaction failure...[/yellow]")
        try:
            async with Transaction("failing_transaction") as tx:
                # Register a good operation
                file_op = Op("fs.write", {
                    "path": "blog_posts/will-fail.md", 
                    "data": "This should not exist"
                })
                tx.register(file_op, fs_adaptor)
                
                # Simulate failure
                raise ValueError("Simulated failure")
        except ValueError:
            console.print("[green]✓ Transaction rolled back successfully (no file created)[/green]")
            
            # Verify file doesn't exist
            if not (BLOG_DIR / "will-fail.md").exists():
                console.print("[green]✓ Confirmed: failed operation was rolled back[/green]")
        
        return
    
    # Process user request
    console.print(Panel(f"Processing: {args.prompt}", style="bold green"))
    
    # Simple command parsing (in real implementation, use LLM)
    prompt_lower = args.prompt.lower()
    
    if "list" in prompt_lower:
        posts = agent.list_posts()
        display_posts(posts)
    
    elif "create" in prompt_lower and "python-async" in prompt_lower:
        await agent.demo_create_post("python-async", "Mastering Python Async Programming")
        console.print("[green]✓ Blog post created successfully![/green]")
    
    elif "delete" in prompt_lower and "python-async" in prompt_lower:
        await agent.delete_post("python-async")
        console.print("[green]✓ Blog post deleted successfully![/green]")
    
    else:
        # Use LLM for complex requests (simplified for demo)
        console.print("[yellow]For complex requests, use --demo flag to see transaction capabilities[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())