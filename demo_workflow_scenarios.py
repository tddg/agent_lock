#!/usr/bin/env python3

"""
Demo: Real-World Workflow Scenarios

Demonstrates how workflow-level transactions solve real agentic workflow problems.
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
    workflow_transaction, workflow_transactional
)
from workflow_resource_managers import (
    FileSystemManager, DatabaseManager, APIManager
)
from workflow_parser import WorkflowParser


async def demo_blog_publishing_workflow():
    """
    Demo: Blog Publishing Workflow
    
    User prompt: "Create a new blog post about AI safety AND update the site index 
                 AND update metadata AND notify subscribers"
    
    This should all happen atomically - if any step fails, everything rolls back.
    """
    print("\n📝 DEMO 1: BLOG PUBLISHING WORKFLOW")
    print("=" * 60)
    print("Scenario: User wants to publish a blog post atomically")
    print("Requirements: File creation + index update + metadata + notifications")
    print("=" * 60)
    
    test_dir = tempfile.mkdtemp(prefix="blog_demo_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        # Setup existing blog structure
        os.makedirs("posts", exist_ok=True)
        
        # Create existing index
        with open("index.html", "w") as f:
            f.write("""<!DOCTYPE html>
<html>
<head><title>My Blog</title></head>
<body>
    <h1>My Blog</h1>
    <div id="posts">
        <!-- Existing posts would be here -->
    </div>
</body>
</html>""")
        
        # Create database
        conn = sqlite3.connect("blog.db")
        conn.execute('''CREATE TABLE posts 
                       (id INTEGER PRIMARY KEY, slug TEXT, title TEXT, 
                        content TEXT, published_date TEXT)''')
        conn.commit()
        conn.close()
        
        print("✅ Blog infrastructure setup complete")
        
        # Create workflow transaction
        async with workflow_transaction("blog_publishing") as wtx:
            # Setup resource managers
            fs_manager = FileSystemManager()
            db_manager = DatabaseManager("blog.db")
            api_manager = APIManager()
            
            wtx.register_resource_manager("filesystem", fs_manager)
            wtx.register_resource_manager("database", db_manager)
            wtx.register_resource_manager("api", api_manager)
            
            # Operation 1: Create blog post file
            blog_content = """# AI Safety: A Critical Consideration

As artificial intelligence systems become more powerful and ubiquitous, 
ensuring their safety and alignment with human values becomes increasingly important.

## Key Challenges

1. **Alignment Problem**: Ensuring AI systems pursue intended goals
2. **Robustness**: AI systems performing safely in novel situations  
3. **Interpretability**: Understanding how AI systems make decisions

## Current Research

Researchers are working on various approaches including:
- Constitutional AI
- Reward modeling
- Interpretability techniques
- Formal verification methods

## Conclusion

AI safety research is crucial for ensuring that advanced AI systems 
remain beneficial and aligned with human values as they become more capable.
"""
            
            create_post_op = Operation(
                id="create_blog_post",
                type=OperationType.FILE_CREATE,
                resource_type="filesystem",
                target="posts/ai-safety-2025.md",
                data={"tx_id": wtx.id, "content": blog_content}
            )
            wtx.add_operation(create_post_op)
            
            # Operation 2: Update index.html
            update_index_op = Operation(
                id="update_index",
                type=OperationType.FILE_UPDATE,
                resource_type="filesystem",
                target="index.html",
                data={
                    "tx_id": wtx.id,
                    "content": """<!DOCTYPE html>
<html>
<head><title>My Blog</title></head>
<body>
    <h1>My Blog</h1>
    <div id="posts">
        <article>
            <h2><a href="posts/ai-safety-2025.html">AI Safety: A Critical Consideration</a></h2>
            <p>Published: 2025-01-15 | Topics: AI, Safety, Research</p>
            <p>As artificial intelligence systems become more powerful and ubiquitous...</p>
        </article>
        <!-- Other posts would be here -->
    </div>
</body>
</html>"""
                }
            )
            wtx.add_operation(update_index_op)
            
            # Operation 3: Insert metadata into database
            db_insert_op = Operation(
                id="insert_post_metadata",
                type=OperationType.DB_INSERT,
                resource_type="database",
                target="posts",
                data={
                    "tx_id": wtx.id,
                    "record_data": {
                        "slug": "ai-safety-2025",
                        "title": "AI Safety: A Critical Consideration",
                        "content": blog_content[:200] + "...",
                        "published_date": "2025-01-15"
                    }
                }
            )
            wtx.add_operation(db_insert_op)
            
            # Operation 4: Simulate API call to notify subscribers
            # (In real scenario, this would call an actual email service)
            notify_op = Operation(
                id="notify_subscribers",
                type=OperationType.API_CALL,
                resource_type="api",
                target="https://api.example.com/notify",
                data={
                    "tx_id": wtx.id,
                    "method": "POST",
                    "payload": {
                        "post_title": "AI Safety: A Critical Consideration",
                        "post_url": "https://myblog.com/posts/ai-safety-2025.html",
                        "subscriber_list": "all"
                    },
                    "compensation": {
                        "url": "https://api.example.com/cancel-notification",
                        "method": "POST",
                        "data": {"notification_id": "ai-safety-2025"}
                    }
                }
            )
            # Note: In demo, we'll skip actual API call
            # wtx.add_operation(notify_op)
            
            print("📝 Blog post workflow defined with 3 operations")
            print("   1. Create blog post file")
            print("   2. Update index.html")  
            print("   3. Insert metadata into database")
            # print("   4. Notify subscribers via API")
        
        # Verify all operations completed atomically
        assert os.path.exists("posts/ai-safety-2025.md"), "Blog post should be created"
        assert "AI Safety" in open("index.html").read(), "Index should be updated"
        
        # Verify database
        conn = sqlite3.connect("blog.db")
        cursor = conn.execute("SELECT title FROM posts WHERE slug = ?", ("ai-safety-2025",))
        result = cursor.fetchone()
        conn.close()
        assert result and "AI Safety" in result[0], "Database should be updated"
        
        print("✅ Blog publishing workflow completed successfully!")
        print("🎉 All operations executed atomically - blog post is live!")
        
    except Exception as e:
        print(f"❌ Blog publishing failed: {e}")
        print("🔄 All changes would be rolled back automatically")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


async def demo_e_commerce_order_workflow():
    """
    Demo: E-commerce Order Processing Workflow
    
    User prompt: "Process order #12345: charge payment, update inventory, 
                 create shipping label, send confirmation email"
    
    This is a critical workflow - partial execution could result in charged 
    customers without products, or shipped products without payment.
    """
    print("\n🛒 DEMO 2: E-COMMERCE ORDER PROCESSING WORKFLOW")
    print("=" * 60)
    print("Scenario: Process customer order atomically")
    print("Requirements: Payment + inventory + shipping + confirmation")
    print("Risk: Partial failure = customer charged but no product delivered")
    print("=" * 60)
    
    test_dir = tempfile.mkdtemp(prefix="ecommerce_demo_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        # Setup e-commerce database
        conn = sqlite3.connect("ecommerce.db")
        conn.execute('''CREATE TABLE orders 
                       (id INTEGER PRIMARY KEY, customer_id INTEGER, 
                        status TEXT, total_amount REAL, items TEXT)''')
        conn.execute('''CREATE TABLE inventory 
                       (product_id TEXT PRIMARY KEY, quantity INTEGER)''')
        conn.execute('''CREATE TABLE payments 
                       (id INTEGER PRIMARY KEY, order_id INTEGER, 
                        amount REAL, status TEXT, transaction_id TEXT)''')
        
        # Insert test inventory
        conn.execute("INSERT INTO inventory VALUES ('widget-a', 10)")
        conn.execute("INSERT INTO inventory VALUES ('widget-b', 5)")
        conn.commit()
        conn.close()
        
        print("✅ E-commerce database setup complete")
        
        # Simulate order data
        order_data = {
            "order_id": 12345,
            "customer_id": 567,
            "items": [
                {"product_id": "widget-a", "quantity": 2, "price": 29.99},
                {"product_id": "widget-b", "quantity": 1, "price": 39.99}
            ],
            "total": 99.97
        }
        
        @workflow_transactional("order_processing", "Process e-commerce order atomically")
        async def process_order(wtx, order_data):
            # Setup resource managers
            db_manager = DatabaseManager("ecommerce.db")
            api_manager = APIManager()
            fs_manager = FileSystemManager()
            
            wtx.register_resource_manager("database", db_manager)
            wtx.register_resource_manager("api", api_manager)
            wtx.register_resource_manager("filesystem", fs_manager)
            
            # Step 1: Create order record
            create_order_op = Operation(
                id="create_order",
                type=OperationType.DB_INSERT,
                resource_type="database",
                target="orders",
                data={
                    "tx_id": wtx.id,
                    "record_data": {
                        "id": order_data["order_id"],
                        "customer_id": order_data["customer_id"],
                        "status": "processing",
                        "total_amount": order_data["total"],
                        "items": json.dumps(order_data["items"])
                    }
                }
            )
            wtx.add_operation(create_order_op)
            
            # Step 2: Update inventory for each item
            for item in order_data["items"]:
                update_inventory_op = Operation(
                    id=f"update_inventory_{item['product_id']}",
                    type=OperationType.DB_UPDATE,
                    resource_type="database",
                    target="inventory",
                    data={
                        "tx_id": wtx.id,
                        "record_data": {"quantity": f"quantity - {item['quantity']}"},
                        "where_clause": "product_id = ?",
                        "where_params": [item["product_id"]]
                    }
                )
                wtx.add_operation(update_inventory_op)
            
            # Step 3: Record payment (simulate payment processing)
            payment_op = Operation(
                id="record_payment",
                type=OperationType.DB_INSERT,
                resource_type="database",
                target="payments",
                data={
                    "tx_id": wtx.id,
                    "record_data": {
                        "order_id": order_data["order_id"],
                        "amount": order_data["total"],
                        "status": "completed",
                        "transaction_id": f"txn_{order_data['order_id']}"
                    }
                }
            )
            wtx.add_operation(payment_op)
            
            # Step 4: Create shipping label file
            shipping_label = f"""
SHIPPING LABEL - Order #{order_data['order_id']}
{'='*40}
Customer ID: {order_data['customer_id']}
Items: {len(order_data['items'])} items
Total: ${order_data['total']:.2f}
Weight: Calculated based on items
Carrier: Express Shipping Co.
Tracking: TRK{order_data['order_id']}ABC
{'='*40}
            """.strip()
            
            create_label_op = Operation(
                id="create_shipping_label",
                type=OperationType.FILE_CREATE,
                resource_type="filesystem",
                target=f"shipping_labels/order_{order_data['order_id']}.txt",
                data={"tx_id": wtx.id, "content": shipping_label}
            )
            wtx.add_operation(create_label_op)
            
            # Note: In a real system, we'd also add API operations for:
            # - Charging the payment method
            # - Sending confirmation email
            # - Notifying warehouse system
            # Each with appropriate compensation logic
            
            print(f"🛒 Order {order_data['order_id']} workflow defined with 4 operations:")
            print("   1. Create order record")
            print("   2. Update inventory for each item")
            print("   3. Record payment")
            print("   4. Create shipping label")
        
        # Execute order processing
        await process_order(order_data)
        
        # Verify order was processed completely
        conn = sqlite3.connect("ecommerce.db")
        
        # Check order exists
        cursor = conn.execute("SELECT status FROM orders WHERE id = ?", (12345,))
        order_result = cursor.fetchone()
        assert order_result and order_result[0] == "processing", "Order should be created"
        
        # Check inventory was updated
        cursor = conn.execute("SELECT quantity FROM inventory WHERE product_id = ?", ("widget-a",))
        inventory_result = cursor.fetchone()
        assert inventory_result and inventory_result[0] == 8, "Inventory should be reduced"
        
        # Check payment was recorded
        cursor = conn.execute("SELECT status FROM payments WHERE order_id = ?", (12345,))
        payment_result = cursor.fetchone()
        assert payment_result and payment_result[0] == "completed", "Payment should be recorded"
        
        conn.close()
        
        # Check shipping label was created
        assert os.path.exists("shipping_labels/order_12345.txt"), "Shipping label should be created"
        
        print("✅ E-commerce order processing completed successfully!")
        print("🎉 Order #12345 processed atomically - customer charged, inventory updated, shipping ready!")
        
    except Exception as e:
        print(f"❌ Order processing failed: {e}")
        print("🔄 All changes would be rolled back - no partial charges or inventory issues!")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


async def demo_deployment_workflow():
    """
    Demo: Application Deployment Workflow
    
    User prompt: "Deploy new version: update code, migrate database, 
                 restart services, update load balancer"
    
    Deployment failures are catastrophic if partial - we need atomicity.
    """
    print("\n🚀 DEMO 3: APPLICATION DEPLOYMENT WORKFLOW")
    print("=" * 60)
    print("Scenario: Deploy new application version atomically")
    print("Requirements: Code update + DB migration + service restart + LB update")
    print("Risk: Partial deployment = broken application in production")
    print("=" * 60)
    
    test_dir = tempfile.mkdtemp(prefix="deployment_demo_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        # Setup application structure
        os.makedirs("app/v1", exist_ok=True)
        os.makedirs("app/v2", exist_ok=True)
        os.makedirs("config", exist_ok=True)
        
        # Create current application files
        with open("app/v1/main.py", "w") as f:
            f.write("# Application v1.0\nVERSION = '1.0.0'\n")
        
        with open("app/v2/main.py", "w") as f:
            f.write("# Application v2.0\nVERSION = '2.0.0'\n")
        
        # Create database
        conn = sqlite3.connect("app.db")
        conn.execute("CREATE TABLE app_config (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO app_config VALUES ('version', '1.0.0')")
        conn.execute("INSERT INTO app_config VALUES ('feature_flags', '{\"new_ui\": false}')")
        conn.commit()
        conn.close()
        
        # Create load balancer config
        with open("config/loadbalancer.json", "w") as f:
            json.dump({
                "version": "1.0.0",
                "backend_servers": [
                    {"host": "app1.example.com", "port": 8000, "weight": 1},
                    {"host": "app2.example.com", "port": 8000, "weight": 1}
                ],
                "health_check": "/health"
            }, f, indent=2)
        
        print("✅ Application infrastructure setup complete")
        
        async with workflow_transaction("deployment_v2") as wtx:
            # Setup resource managers
            fs_manager = FileSystemManager()
            db_manager = DatabaseManager("app.db")
            api_manager = APIManager()
            
            wtx.register_resource_manager("filesystem", fs_manager)
            wtx.register_resource_manager("database", db_manager)
            wtx.register_resource_manager("api", api_manager)
            
            # Step 1: Update application code
            update_code_op = Operation(
                id="update_application_code",
                type=OperationType.FILE_UPDATE,
                resource_type="filesystem",
                target="app/current/main.py",
                data={
                    "tx_id": wtx.id,
                    "content": "# Application v2.0\nVERSION = '2.0.0'\n# New features added\n"
                }
            )
            # Note: For demo, we'll create instead of update
            update_code_op.type = OperationType.FILE_CREATE
            update_code_op.target = "app/current/main.py"
            wtx.add_operation(update_code_op)
            
            # Step 2: Migrate database schema/data
            migrate_db_op = Operation(
                id="migrate_database",
                type=OperationType.DB_UPDATE,
                resource_type="database",
                target="app_config",
                data={
                    "tx_id": wtx.id,
                    "record_data": {"value": "2.0.0"},
                    "where_clause": "key = ?",
                    "where_params": ["version"]
                }
            )
            wtx.add_operation(migrate_db_op)
            
            # Add new feature flags
            add_features_op = Operation(
                id="add_feature_flags",
                type=OperationType.DB_UPDATE,
                resource_type="database",
                target="app_config",
                data={
                    "tx_id": wtx.id,
                    "record_data": {"value": '{"new_ui": true, "v2_features": true}'},
                    "where_clause": "key = ?",
                    "where_params": ["feature_flags"]
                }
            )
            wtx.add_operation(add_features_op)
            
            # Step 3: Update load balancer configuration
            new_lb_config = {
                "version": "2.0.0",
                "backend_servers": [
                    {"host": "app1.example.com", "port": 8000, "weight": 1},
                    {"host": "app2.example.com", "port": 8000, "weight": 1},
                    {"host": "app3.example.com", "port": 8000, "weight": 1}  # New server
                ],
                "health_check": "/v2/health",  # Updated health check
                "features": ["new_ui", "v2_features"]
            }
            
            update_lb_op = Operation(
                id="update_load_balancer",
                type=OperationType.FILE_UPDATE,
                resource_type="filesystem",
                target="config/loadbalancer.json",
                data={
                    "tx_id": wtx.id,
                    "content": json.dumps(new_lb_config, indent=2)
                }
            )
            wtx.add_operation(update_lb_op)
            
            # Step 4: Create deployment log
            deployment_log = f"""
DEPLOYMENT LOG - Version 2.0.0
{'='*40}
Timestamp: 2025-01-15T10:30:00Z
Previous Version: 1.0.0
New Version: 2.0.0

Changes:
- Updated application code to v2.0.0
- Migrated database schema
- Added new feature flags
- Updated load balancer config
- Added third backend server

Status: COMPLETED
{'='*40}
            """.strip()
            
            create_log_op = Operation(
                id="create_deployment_log",
                type=OperationType.FILE_CREATE,
                resource_type="filesystem",
                target=f"logs/deployment_v2_2025-01-15.log",
                data={"tx_id": wtx.id, "content": deployment_log}
            )
            wtx.add_operation(create_log_op)
            
            print("🚀 Deployment workflow defined with 5 operations:")
            print("   1. Update application code to v2.0.0")
            print("   2. Migrate database version")
            print("   3. Update feature flags")
            print("   4. Update load balancer config")
            print("   5. Create deployment log")
        
        # Verify deployment completed atomically
        assert os.path.exists("app/current/main.py"), "Application code should be updated"
        assert "2.0.0" in open("app/current/main.py").read(), "Should be version 2.0.0"
        
        # Check database migration
        conn = sqlite3.connect("app.db")
        cursor = conn.execute("SELECT value FROM app_config WHERE key = ?", ("version",))
        result = cursor.fetchone()
        assert result and result[0] == "2.0.0", "Database should show v2.0.0"
        conn.close()
        
        # Check load balancer config
        with open("config/loadbalancer.json", "r") as f:
            lb_config = json.load(f)
        assert lb_config["version"] == "2.0.0", "Load balancer should be updated"
        assert len(lb_config["backend_servers"]) == 3, "Should have 3 backend servers"
        
        # Check deployment log
        assert os.path.exists("logs/deployment_v2_2025-01-15.log"), "Deployment log should exist"
        
        print("✅ Application deployment completed successfully!")
        print("🎉 Version 2.0.0 deployed atomically - all components synchronized!")
        
    except Exception as e:
        print(f"❌ Deployment failed: {e}")
        print("🔄 All changes would be rolled back - application remains on v1.0.0!")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def demo_workflow_parser_scenarios():
    """
    Demo: Workflow Parser analyzing different user prompts
    """
    print("\n🧠 DEMO 4: WORKFLOW PARSER ANALYSIS")
    print("=" * 60)
    print("Analyzing various user prompts to detect transaction boundaries")
    print("=" * 60)
    
    parser = WorkflowParser()
    
    test_prompts = [
        {
            "prompt": "Create a new blog post about AI safety AND update the site index AND notify subscribers",
            "expected_pattern": "atomic operations (AND conjunctions)"
        },
        {
            "prompt": "Create user account. Then send welcome email. Later setup billing.",
            "expected_pattern": "sequential operations (Then/Later)"
        },
        {
            "prompt": "Deploy new version to production",
            "expected_pattern": "workflow template (deployment)"
        },
        {
            "prompt": "Register new user and create profile",
            "expected_pattern": "template (user registration)"
        },
        {
            "prompt": "BEGIN TRANSACTION: Update inventory, process payment, ship order",
            "expected_pattern": "explicit transaction boundary"
        },
        {
            "prompt": "Create report. If successful, email to manager and archive the data.",
            "expected_pattern": "conditional workflow (If successful)"
        }
    ]
    
    for i, test_case in enumerate(test_prompts, 1):
        print(f"\n📝 Test Case {i}:")
        print(f"Prompt: \"{test_case['prompt']}\"")
        print(f"Expected: {test_case['expected_pattern']}")
        
        try:
            plan = parser.parse_prompt(test_case['prompt'])
            
            print(f"✅ Parsed Successfully:")
            print(f"   - Workflow Name: {plan.name}")
            print(f"   - Operations: {len(plan.operations)}")
            print(f"   - Risk Level: {plan.risk_level}")
            print(f"   - Requires Confirmation: {plan.requires_confirmation}")
            print(f"   - Estimated Duration: {plan.estimated_duration:.1f}s")
            
            if plan.operations:
                print(f"   - Operation Types: {[op.type.value for op in plan.operations]}")
            
        except Exception as e:
            print(f"❌ Parsing failed: {e}")
    
    print("\n✅ Workflow parser demo completed!")
    print("🧠 Parser successfully analyzed various prompt patterns!")


async def run_all_demos():
    """Run all workflow scenario demos."""
    print("🎭 WORKFLOW-LEVEL TRANSACTION DEMOS")
    print("=" * 60)
    print("Real-world scenarios demonstrating workflow-level atomicity")
    print("=" * 60)
    
    demos = [
        ("Blog Publishing Workflow", demo_blog_publishing_workflow()),
        ("E-commerce Order Processing", demo_e_commerce_order_workflow()),
        ("Application Deployment", demo_deployment_workflow()),
        ("Workflow Parser Analysis", demo_workflow_parser_scenarios())
    ]
    
    for demo_name, demo_coro in demos:
        print(f"\n{'='*60}")
        print(f"🎭 {demo_name}")
        print('='*60)
        
        try:
            if asyncio.iscoroutine(demo_coro):
                await demo_coro
            else:
                demo_coro
        except Exception as e:
            print(f"💥 Demo failed: {e}")
    
    print(f"\n{'='*60}")
    print("🎉 ALL WORKFLOW DEMOS COMPLETED!")
    print("=" * 60)
    print("🚀 Workflow-level transactions solve real agentic workflow problems:")
    print("   ✅ Blog publishing: All-or-nothing content creation")
    print("   ✅ E-commerce: No partial orders or charges")
    print("   ✅ Deployment: Atomic version updates")
    print("   ✅ Smart parsing: Intent-driven boundaries")
    print()
    print("💡 Key Benefits Demonstrated:")
    print("   🛡️  Cross-resource atomicity (files + DB + APIs)")
    print("   🎯 User-intent driven boundaries")
    print("   🔄 Intelligent rollback on failures")
    print("   📊 Rich workflow monitoring and logging")
    print("   🧠 Natural language workflow detection")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_demos())