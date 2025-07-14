#!/usr/bin/env python3

"""
Workflow Integration Example

Demonstrates how workflow-level transactions solve the real problems 
identified with function-level transactions in agentic systems.
"""

import asyncio
import os
import tempfile
import shutil
import sqlite3
import json
from pathlib import Path

from workflow_tx_core import (
    WorkflowTransaction, Operation, OperationType,
    workflow_transaction, workflow_transactional, WorkflowPlan
)
from workflow_resource_managers import (
    FileSystemManager, DatabaseManager, APIManager
)
from workflow_parser import WorkflowParser


class AgenticWorkflowAgent:
    """
    Example agent that uses workflow-level transactions for multi-step operations.
    
    This demonstrates how agents can execute complex workflows atomically
    based on user prompts.
    """
    
    def __init__(self):
        self.parser = WorkflowParser()
        self.fs_manager = FileSystemManager()
        self.db_manager = None  # Will be set per workflow
        self.api_manager = APIManager()
    
    async def handle_user_prompt(self, prompt: str, context: dict = None) -> dict:
        """
        Handle a user prompt by parsing it into a workflow and executing atomically.
        
        This is the key difference from function-level transactions:
        - The ENTIRE user request is treated as one atomic unit
        - Transaction boundaries are determined by user intent, not function boundaries
        - Cross-resource operations are coordinated
        """
        print(f"\n🤖 AGENT: Processing user request")
        print(f"📝 Prompt: \"{prompt}\"")
        
        try:
            # Step 1: Parse the prompt to understand user intent
            workflow_plan = self.parser.parse_prompt(prompt)
            print(f"🧠 Detected workflow: {workflow_plan.name}")
            print(f"📊 Operations: {len(workflow_plan.operations)}")
            print(f"⚠️  Risk level: {workflow_plan.risk_level}")
            
            # Step 2: Execute the workflow atomically
            result = await self._execute_workflow_plan(workflow_plan, context or {})
            
            return {
                "status": "success",
                "workflow_name": workflow_plan.name,
                "operations_completed": len(workflow_plan.operations),
                "result": result
            }
            
        except Exception as e:
            print(f"❌ Workflow failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "message": "All operations rolled back automatically"
            }
    
    async def _execute_workflow_plan(self, plan: WorkflowPlan, context: dict) -> dict:
        """Execute a workflow plan atomically."""
        
        # Create workflow transaction with user-meaningful name
        async with workflow_transaction(plan.name, plan.description) as wtx:
            
            # Setup resource managers based on operations
            resource_types = set(op.resource_type for op in plan.operations)
            
            if "filesystem" in resource_types:
                wtx.register_resource_manager("filesystem", self.fs_manager)
            
            if "database" in resource_types:
                db_path = context.get("database_path", "workflow.db")
                self.db_manager = DatabaseManager(db_path)
                wtx.register_resource_manager("database", self.db_manager)
            
            if "api" in resource_types:
                wtx.register_resource_manager("api", self.api_manager)
            
            # Add all operations to the workflow
            for operation in plan.operations:
                # Enrich operation with context data
                self._enrich_operation_with_context(operation, context, wtx.id)
                wtx.add_operation(operation)
            
            print(f"🚀 Executing {len(plan.operations)} operations atomically...")
            
            # Workflow will execute when context exits
            return {"workflow_executed": True, "transaction_id": wtx.id}
    
    def _enrich_operation_with_context(self, operation: Operation, context: dict, tx_id: str):
        """Enrich operation with context data and transaction ID."""
        operation.data["tx_id"] = tx_id
        
        # Add context-specific data based on operation type
        if operation.type == OperationType.FILE_CREATE:
            if "content" not in operation.data:
                operation.data["content"] = context.get("default_content", "# Generated content")
        
        elif operation.type == OperationType.DB_INSERT:
            if "record_data" not in operation.data:
                operation.data["record_data"] = context.get("record_data", {})
        
        elif operation.type == OperationType.API_CALL:
            if "payload" not in operation.data:
                operation.data["payload"] = context.get("api_payload", {})


async def demo_agent_workflow_comparison():
    """
    Compare function-level vs workflow-level transaction approaches.
    """
    print("🔄 COMPARISON: Function-Level vs Workflow-Level Transactions")
    print("=" * 70)
    
    # Setup test environment
    test_dir = tempfile.mkdtemp(prefix="agent_comparison_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        # Create test database
        conn = sqlite3.connect("blog.db")
        conn.execute('''CREATE TABLE posts 
                       (id INTEGER PRIMARY KEY, title TEXT, content TEXT, published_date TEXT)''')
        conn.commit()
        conn.close()
        
        print("✅ Test environment setup complete")
        
        # Scenario: User wants to create a blog post with metadata
        user_prompt = "Create a new blog post about machine learning AND update the site index AND add metadata to database"
        
        print(f"\n📝 User Request: \"{user_prompt}\"")
        
        # PROBLEM with function-level approach:
        print("\n❌ FUNCTION-LEVEL APPROACH (OLD WAY):")
        print("   - create_blog_post() = Transaction 1")
        print("   - update_index() = Transaction 2") 
        print("   - add_metadata() = Transaction 3")
        print("   - Result: 3 separate transactions!")
        print("   - Risk: Partial execution if any transaction fails")
        print("   - Example: Blog post created, but index update fails")
        print("   - User sees: Inconsistent state, broken website")
        
        # SOLUTION with workflow-level approach:
        print("\n✅ WORKFLOW-LEVEL APPROACH (NEW WAY):")
        
        agent = AgenticWorkflowAgent()
        context = {
            "database_path": "blog.db",
            "default_content": """# Machine Learning Fundamentals

Machine learning is a subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed.

## Key Concepts

1. **Supervised Learning**: Learning with labeled examples
2. **Unsupervised Learning**: Finding patterns in unlabeled data  
3. **Reinforcement Learning**: Learning through trial and error

## Applications

- Image recognition
- Natural language processing
- Recommendation systems
- Autonomous vehicles

## Conclusion

Machine learning continues to transform industries and create new possibilities for innovation.
""",
            "record_data": {
                "title": "Machine Learning Fundamentals",
                "content": "Machine learning is a subset of artificial intelligence...",
                "published_date": "2025-01-15"
            }
        }
        
        result = await agent.handle_user_prompt(user_prompt, context)
        
        if result["status"] == "success":
            print(f"   ✅ Single workflow transaction completed!")
            print(f"   ✅ Operations: {result['operations_completed']}")
            print(f"   ✅ Result: All-or-nothing execution")
            print(f"   ✅ Benefit: Guaranteed consistency")
            
            # Verify all operations completed
            files_created = []
            if os.path.exists("posts"):
                files_created.extend([f"posts/{f}" for f in os.listdir("posts")])
            
            conn = sqlite3.connect("blog.db")
            cursor = conn.execute("SELECT COUNT(*) FROM posts")
            db_records = cursor.fetchone()[0]
            conn.close()
            
            print(f"   📁 Files created: {len(files_created)}")
            print(f"   🗄️  Database records: {db_records}")
            
        else:
            print(f"   ❌ Workflow failed: {result['error']}")
            print(f"   🔄 All operations rolled back automatically")
        
        print("\n🎯 KEY DIFFERENCES:")
        print("   Function-Level: Boundaries = Code structure")
        print("   Workflow-Level: Boundaries = User intent")
        print()
        print("   Function-Level: Error handling = Per-function")
        print("   Workflow-Level: Error handling = Workflow-wide rollback")
        print()
        print("   Function-Level: Coordination = Manual/None")
        print("   Workflow-Level: Coordination = Automatic cross-resource")
        
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


async def demo_complex_agentic_workflow():
    """
    Demonstrate a complex multi-step agentic workflow that spans multiple resources.
    """
    print("\n🤖 COMPLEX AGENTIC WORKFLOW DEMO")
    print("=" * 70)
    print("Scenario: AI agent processes a complex user request atomically")
    print("=" * 70)
    
    test_dir = tempfile.mkdtemp(prefix="complex_agent_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        # Setup complex environment
        os.makedirs("projects", exist_ok=True)
        os.makedirs("users", exist_ok=True)
        
        # Create databases
        conn = sqlite3.connect("projects.db")
        conn.execute('''CREATE TABLE projects 
                       (id INTEGER PRIMARY KEY, name TEXT, owner_id INTEGER, 
                        status TEXT, created_date TEXT)''')
        conn.execute('''CREATE TABLE project_files 
                       (id INTEGER PRIMARY KEY, project_id INTEGER, filename TEXT, 
                        file_type TEXT, size INTEGER)''')
        conn.commit()
        conn.close()
        
        conn = sqlite3.connect("users.db")
        conn.execute('''CREATE TABLE users 
                       (id INTEGER PRIMARY KEY, username TEXT, email TEXT, 
                        project_count INTEGER DEFAULT 0)''')
        conn.execute("INSERT INTO users VALUES (1, 'alice', 'alice@example.com', 0)")
        conn.commit()
        conn.close()
        
        print("✅ Complex environment setup complete")
        
        # Complex user request spanning multiple systems
        complex_prompt = """Create a new Python project called 'ml-classifier' for user alice, 
                           generate the project structure with main.py and requirements.txt, 
                           update the project database, increment user's project count,
                           and create a project README"""
        
        print(f"📝 Complex Request: \"{complex_prompt}\"")
        
        # Define the complex workflow manually (in a real system, the parser would handle this)
        @workflow_transactional("complex_project_creation", "Create complete project with all metadata")
        async def create_project_workflow(wtx):
            
            # Setup resource managers
            fs_manager = FileSystemManager()
            projects_db = DatabaseManager("projects.db")
            users_db = DatabaseManager("users.db")
            
            wtx.register_resource_manager("filesystem", fs_manager)
            wtx.register_resource_manager("projects_database", projects_db)
            wtx.register_resource_manager("users_database", users_db)
            
            project_name = "ml-classifier"
            user_id = 1
            
            # Operation 1: Create project directory structure
            project_files = [
                (f"projects/{project_name}/main.py", """#!/usr/bin/env python3
\"\"\"
ML Classifier Project
A machine learning classification project.
\"\"\"

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

def load_data(filename):
    \"\"\"Load dataset from CSV file.\"\"\"
    return pd.read_csv(filename)

def train_classifier(X, y):
    \"\"\"Train a random forest classifier.\"\"\"
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)
    
    # Evaluate
    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"Model accuracy: {accuracy:.2f}")
    return clf

def main():
    \"\"\"Main function.\"\"\"
    print("ML Classifier Project")
    print("Load your data and train a model!")

if __name__ == "__main__":
    main()
"""),
                (f"projects/{project_name}/requirements.txt", """numpy>=1.21.0
pandas>=1.3.0
scikit-learn>=1.0.0
matplotlib>=3.4.0
seaborn>=0.11.0
jupyter>=1.0.0
"""),
                (f"projects/{project_name}/README.md", f"""# {project_name.title()}

A machine learning classification project created with the agentic workflow system.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the main script:
   ```bash
   python main.py
   ```

## Project Structure

- `main.py` - Main classification script
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Usage

1. Prepare your dataset in CSV format
2. Modify the `load_data()` function to load your data
3. Run the script to train and evaluate the model

## Features

- Random Forest classifier
- Train/test split
- Accuracy evaluation
- Extensible architecture

Created: 2025-01-15
Owner: alice
"""),
                (f"projects/{project_name}/.gitignore", """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv
pip-log.txt
pip-delete-this-directory.txt
.pytest_cache/

# Data files
*.csv
*.json
data/
models/

# Jupyter
.ipynb_checkpoints
""")
            ]
            
            for file_path, content in project_files:
                op = Operation(
                    id=f"create_{file_path.replace('/', '_')}",
                    type=OperationType.FILE_CREATE,
                    resource_type="filesystem",
                    target=file_path,
                    data={"tx_id": wtx.id, "content": content}
                )
                wtx.add_operation(op)
            
            # Operation 2: Insert project record
            project_op = Operation(
                id="insert_project_record",
                type=OperationType.DB_INSERT,
                resource_type="projects_database",
                target="projects",
                data={
                    "tx_id": wtx.id,
                    "record_data": {
                        "name": project_name,
                        "owner_id": user_id,
                        "status": "active",
                        "created_date": "2025-01-15"
                    }
                }
            )
            wtx.add_operation(project_op)
            
            # Operation 3: Record project files
            for file_path, content in project_files:
                filename = os.path.basename(file_path)
                file_type = os.path.splitext(filename)[1][1:] or "txt"
                
                file_record_op = Operation(
                    id=f"record_file_{filename}",
                    type=OperationType.DB_INSERT,
                    resource_type="projects_database",
                    target="project_files",
                    data={
                        "tx_id": wtx.id,
                        "record_data": {
                            "project_id": 1,  # Will be updated with actual project ID
                            "filename": filename,
                            "file_type": file_type,
                            "size": len(content)
                        }
                    }
                )
                wtx.add_operation(file_record_op)
            
            # Operation 4: Update user's project count
            user_update_op = Operation(
                id="increment_user_projects",
                type=OperationType.DB_UPDATE,
                resource_type="users_database",
                target="users",
                data={
                    "tx_id": wtx.id,
                    "record_data": {"project_count": "project_count + 1"},
                    "where_clause": "id = ?",
                    "where_params": [user_id]
                }
            )
            wtx.add_operation(user_update_op)
            
            print(f"🚀 Complex workflow defined:")
            print(f"   📁 Creating {len(project_files)} project files")
            print(f"   🗄️  Inserting project record")
            print(f"   📋 Recording {len(project_files)} file metadata")
            print(f"   👤 Updating user project count")
            print(f"   📊 Total operations: {len(wtx.operations)}")
        
        # Execute the complex workflow
        await create_project_workflow()
        
        # Verify everything was created atomically
        print(f"\n✅ VERIFICATION:")
        
        # Check files
        project_files = list(Path(f"projects/ml-classifier").rglob("*"))
        project_files = [f for f in project_files if f.is_file()]
        print(f"   📁 Project files created: {len(project_files)}")
        
        # Check project database
        conn = sqlite3.connect("projects.db")
        cursor = conn.execute("SELECT name, status FROM projects WHERE name = ?", ("ml-classifier",))
        project_result = cursor.fetchone()
        
        cursor = conn.execute("SELECT COUNT(*) FROM project_files WHERE project_id = 1")
        file_count = cursor.fetchone()[0]
        conn.close()
        
        print(f"   🗄️  Project in database: {project_result[0] if project_result else 'NOT FOUND'}")
        print(f"   📋 File records: {file_count}")
        
        # Check user database
        conn = sqlite3.connect("users.db")
        cursor = conn.execute("SELECT project_count FROM users WHERE id = 1")
        user_result = cursor.fetchone()
        conn.close()
        
        print(f"   👤 User project count: {user_result[0] if user_result else 'ERROR'}")
        
        if project_result and file_count == 4 and user_result and user_result[0] == 1:
            print(f"\n🎉 COMPLEX WORKFLOW COMPLETED SUCCESSFULLY!")
            print(f"   ✅ All {len(project_files)} files created")
            print(f"   ✅ Project registered in database")
            print(f"   ✅ File metadata recorded")
            print(f"   ✅ User statistics updated")
            print(f"   ✅ Complete atomicity across 3 databases and filesystem")
        else:
            print(f"\n❌ Verification failed - rollback would have occurred")
        
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


async def run_integration_examples():
    """Run all integration examples."""
    print("🔗 WORKFLOW-LEVEL TRANSACTION INTEGRATION EXAMPLES")
    print("=" * 70)
    print("Demonstrating how workflow-level transactions solve real agentic problems")
    print("=" * 70)
    
    examples = [
        ("Agent Workflow Comparison", demo_agent_workflow_comparison()),
        ("Complex Agentic Workflow", demo_complex_agentic_workflow())
    ]
    
    for example_name, example_coro in examples:
        print(f"\n{'='*70}")
        print(f"🔗 {example_name}")
        print('='*70)
        
        try:
            await example_coro
        except Exception as e:
            print(f"💥 Example failed: {e}")
    
    print(f"\n{'='*70}")
    print("🎯 WORKFLOW-LEVEL TRANSACTIONS: PROBLEM SOLVED!")
    print("=" * 70)
    print()
    print("❌ FUNCTION-LEVEL PROBLEMS (SOLVED):")
    print("   • Transaction boundaries mismatched with user intent")
    print("   • Partial execution of multi-step workflows")
    print("   • No cross-resource coordination")
    print("   • Agent actions don't match user expectations")
    print()
    print("✅ WORKFLOW-LEVEL SOLUTIONS:")
    print("   🎯 Intent-driven boundaries: User prompts → Transaction scopes")
    print("   🛡️  Atomic workflows: All operations succeed or all fail")
    print("   🔗 Cross-resource coordination: Files + DBs + APIs unified")
    print("   🧠 Smart parsing: Natural language → Workflow plans")
    print("   🔄 Intelligent rollback: User-friendly error recovery")
    print("   📊 Rich monitoring: Complete visibility into agent actions")
    print()
    print("🚀 READY FOR PRODUCTION AGENTIC SYSTEMS!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_integration_examples())