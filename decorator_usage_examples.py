#!/usr/bin/env python3

"""
Real-world usage examples for workflow-aware decorators.

Shows how existing agent code can be made transactional with minimal changes.
"""

import asyncio
import os
import sqlite3
import json
import time
from typing import List, Dict
from workflow_decorators import auto_transactional, workflow_atomic, transactional


# Example 1: Blog Publishing System
# =================================

@auto_transactional(name="blog_publishing", debug=True)
def publish_blog_post(title: str, content: str, tags: List[str]) -> str:
    """
    Original blog publishing code with ZERO changes except for the decorator.
    
    This function creates a blog post file, updates the database, regenerates
    the index, and notifies subscribers. If ANY step fails, ALL changes are
    automatically rolled back.
    """
    # Create post file
    post_slug = title.lower().replace(" ", "-").replace("'", "")
    post_path = f"posts/{post_slug}.md"
    
    # Ensure posts directory exists
    os.makedirs("posts", exist_ok=True)
    
    # Write blog post
    with open(post_path, 'w') as f:
        f.write(f"# {title}\n\n{content}\n\n---\nTags: {', '.join(tags)}")
    
    # Update database
    conn = sqlite3.connect("blog.db")
    
    # Create tables if they don't exist
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                   (id INTEGER PRIMARY KEY, title TEXT, slug TEXT, path TEXT, 
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS post_tags 
                   (post_id INTEGER, tag TEXT, 
                    FOREIGN KEY(post_id) REFERENCES posts(id))''')
    
    # Insert post
    cursor = conn.execute(
        "INSERT INTO posts (title, slug, path) VALUES (?, ?, ?) RETURNING id",
        (title, post_slug, post_path)
    )
    post_id = cursor.fetchone()[0]
    
    # Insert tags
    for tag in tags:
        conn.execute("INSERT INTO post_tags (post_id, tag) VALUES (?, ?)", (post_id, tag))
    
    conn.commit()
    conn.close()
    
    # Update site index
    update_site_index()
    
    # Generate RSS feed
    generate_rss_feed()
    
    print(f"✅ Blog post '{title}' published successfully!")
    return post_path


def update_site_index():
    """Update the main site index with latest posts."""
    conn = sqlite3.connect("blog.db")
    cursor = conn.execute(
        "SELECT title, slug, created_at FROM posts ORDER BY created_at DESC LIMIT 5"
    )
    recent_posts = cursor.fetchall()
    conn.close()
    
    # Generate index HTML
    html = "<html><body><h1>My Blog</h1><ul>"
    for title, slug, created_at in recent_posts:
        html += f'<li><a href="posts/{slug}.html">{title}</a> ({created_at})</li>'
    html += "</ul></body></html>"
    
    with open("index.html", "w") as f:
        f.write(html)


def generate_rss_feed():
    """Generate RSS feed for the blog."""
    conn = sqlite3.connect("blog.db")
    cursor = conn.execute(
        "SELECT title, slug, created_at FROM posts ORDER BY created_at DESC LIMIT 10"
    )
    posts = cursor.fetchall()
    conn.close()
    
    # Simple RSS generation
    rss = '<?xml version="1.0"?><rss version="2.0"><channel><title>My Blog</title>'
    for title, slug, created_at in posts:
        rss += f"<item><title>{title}</title><link>posts/{slug}.html</link></item>"
    rss += "</channel></rss>"
    
    with open("feed.xml", "w") as f:
        f.write(rss)


# Example 2: E-commerce Order Processing
# =====================================

@auto_transactional(
    name="order_processing",
    timeout=120,  # Allow 2 minutes for order processing
    debug=True
)
def process_customer_order(customer_id: int, items: List[Dict], payment_info: Dict) -> int:
    """
    Process a customer order with automatic transaction management.
    
    This simulates a complex e-commerce workflow that involves:
    - Inventory validation and reservation
    - Payment processing simulation
    - Order record creation
    - Inventory updates
    - Customer notification
    
    If ANY step fails, the entire order is rolled back automatically.
    """
    print(f"🛒 Processing order for customer {customer_id} with {len(items)} items")
    
    # 1. Validate and reserve inventory
    total_amount = 0
    reserved_items = []
    
    conn = sqlite3.connect("ecommerce.db")
    
    # Create tables if needed
    conn.execute('''CREATE TABLE IF NOT EXISTS inventory 
                   (sku TEXT PRIMARY KEY, name TEXT, price REAL, stock INTEGER)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS orders 
                   (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL, 
                    status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS order_items 
                   (order_id INTEGER, sku TEXT, quantity INTEGER, price REAL)''')
    
    # Check inventory and calculate total
    for item in items:
        sku = item['sku']
        quantity = item['quantity']
        
        cursor = conn.execute("SELECT name, price, stock FROM inventory WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"Product {sku} not found")
        
        name, price, stock = row
        
        if stock < quantity:
            raise ValueError(f"Insufficient inventory for {name}: requested {quantity}, available {stock}")
        
        # Reserve inventory (reduce stock)
        conn.execute("UPDATE inventory SET stock = stock - ? WHERE sku = ?", (quantity, sku))
        
        total_amount += price * quantity
        reserved_items.append({
            'sku': sku,
            'name': name,
            'quantity': quantity,
            'price': price
        })
    
    print(f"💰 Order total: ${total_amount:.2f}")
    
    # 2. Simulate payment processing
    if not process_payment(payment_info, total_amount):
        raise ValueError("Payment processing failed")
    
    # 3. Create order record
    cursor = conn.execute(
        "INSERT INTO orders (customer_id, total, status) VALUES (?, ?, 'confirmed') RETURNING id",
        (customer_id, total_amount)
    )
    order_id = cursor.fetchone()[0]
    
    # 4. Add order items
    for item in reserved_items:
        conn.execute(
            "INSERT INTO order_items (order_id, sku, quantity, price) VALUES (?, ?, ?, ?)",
            (order_id, item['sku'], item['quantity'], item['price'])
        )
    
    conn.commit()
    conn.close()
    
    # 5. Generate order confirmation
    generate_order_confirmation(order_id, customer_id, reserved_items, total_amount)
    
    print(f"✅ Order {order_id} processed successfully!")
    return order_id


def process_payment(payment_info: Dict, amount: float) -> bool:
    """Simulate payment processing."""
    # In real implementation, this would call payment gateway
    print(f"💳 Processing payment of ${amount:.2f}")
    
    # Simulate payment validation
    if payment_info.get('card_number') == '0000':
        print("❌ Payment failed: Invalid card number")
        return False
    
    # Simulate network delay
    time.sleep(0.1)
    
    print("✅ Payment processed successfully")
    return True


def generate_order_confirmation(order_id: int, customer_id: int, items: List[Dict], total: float):
    """Generate order confirmation file."""
    confirmation = {
        'order_id': order_id,
        'customer_id': customer_id,
        'items': items,
        'total': total,
        'timestamp': time.time()
    }
    
    os.makedirs("confirmations", exist_ok=True)
    with open(f"confirmations/order_{order_id}.json", "w") as f:
        json.dump(confirmation, f, indent=2)


# Example 3: Data Processing Pipeline
# ==================================

@workflow_atomic(name="data_pipeline", debug=True)
def process_data_pipeline(input_file: str, output_dir: str) -> str:
    """
    Data processing pipeline that transforms and saves data.
    
    Shows how existing data science/ETL code can become transactional
    with just a decorator.
    """
    print(f"📊 Processing data pipeline: {input_file} -> {output_dir}")
    
    # 1. Read and validate input data
    with open(input_file, 'r') as f:
        input_data = json.load(f)
    
    if not isinstance(input_data, list):
        raise ValueError("Input data must be a list")
    
    print(f"📥 Loaded {len(input_data)} records")
    
    # 2. Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # 3. Clean and transform data
    cleaned_data = []
    for record in input_data:
        if 'name' in record and 'value' in record:
            cleaned_record = {
                'name': record['name'].strip().title(),
                'value': float(record['value']),
                'processed_at': time.time()
            }
            cleaned_data.append(cleaned_record)
    
    print(f"🧹 Cleaned {len(cleaned_data)} valid records")
    
    # 4. Save intermediate results
    intermediate_file = f"{output_dir}/intermediate.json"
    with open(intermediate_file, 'w') as f:
        json.dump(cleaned_data, f, indent=2)
    
    # 5. Generate summary statistics
    total_value = sum(record['value'] for record in cleaned_data)
    avg_value = total_value / len(cleaned_data) if cleaned_data else 0
    
    summary = {
        'total_records': len(cleaned_data),
        'total_value': total_value,
        'average_value': avg_value,
        'processing_time': time.time()
    }
    
    # 6. Save summary
    summary_file = f"{output_dir}/summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # 7. Update processing log database
    conn = sqlite3.connect("processing_log.db")
    conn.execute('''CREATE TABLE IF NOT EXISTS processing_runs 
                   (id INTEGER PRIMARY KEY, input_file TEXT, output_dir TEXT, 
                    records_processed INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.execute(
        "INSERT INTO processing_runs (input_file, output_dir, records_processed) VALUES (?, ?, ?)",
        (input_file, output_dir, len(cleaned_data))
    )
    conn.commit()
    conn.close()
    
    print(f"✅ Pipeline completed: {len(cleaned_data)} records processed")
    return summary_file


# Example 4: User Account Management
# =================================

@transactional(name="user_account_creation", debug=True)
def create_user_account(username: str, email: str, profile_data: Dict) -> int:
    """
    Create a new user account with profile and settings.
    
    Demonstrates how user management code can be made atomic.
    """
    print(f"👤 Creating user account: {username} ({email})")
    
    # 1. Validate input
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters")
    
    if '@' not in email:
        raise ValueError("Invalid email address")
    
    # 2. Set up database
    conn = sqlite3.connect("users.db")
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                   (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS user_profiles 
                   (user_id INTEGER, profile_data TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS user_settings 
                   (user_id INTEGER, setting_key TEXT, setting_value TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # 3. Check if user already exists
    cursor = conn.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
    if cursor.fetchone():
        raise ValueError("Username or email already exists")
    
    # 4. Create user record
    cursor = conn.execute(
        "INSERT INTO users (username, email) VALUES (?, ?) RETURNING id",
        (username, email)
    )
    user_id = cursor.fetchone()[0]
    
    # 5. Create profile
    conn.execute(
        "INSERT INTO user_profiles (user_id, profile_data) VALUES (?, ?)",
        (user_id, json.dumps(profile_data))
    )
    
    # 6. Set default settings
    default_settings = {
        'theme': 'light',
        'notifications': 'enabled',
        'language': 'en'
    }
    
    for key, value in default_settings.items():
        conn.execute(
            "INSERT INTO user_settings (user_id, setting_key, setting_value) VALUES (?, ?, ?)",
            (user_id, key, value)
        )
    
    conn.commit()
    conn.close()
    
    # 7. Create user directory
    user_dir = f"user_profiles/{username}"
    os.makedirs(user_dir, exist_ok=True)
    
    # 8. Create welcome file
    welcome_file = f"{user_dir}/welcome.txt"
    with open(welcome_file, 'w') as f:
        f.write(f"Welcome {username}!\n\nYour account has been created successfully.\n")
    
    # 9. Create user config file
    config_file = f"{user_dir}/config.json"
    config = {
        'user_id': user_id,
        'username': username,
        'email': email,
        'created_at': time.time()
    }
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ User account created successfully: ID {user_id}")
    return user_id


# Demonstration functions
# ======================

def demo_blog_publishing():
    """Demonstrate the blog publishing workflow."""
    print("\n🎯 DEMO: Blog Publishing System")
    print("=" * 50)
    
    try:
        # This will create files, update database, generate index, etc.
        # All atomically - if any step fails, everything rolls back
        post_path = publish_blog_post(
            title="Getting Started with Workflow Transactions",
            content="Workflow transactions make it easy to coordinate multiple operations...",
            tags=["programming", "transactions", "python"]
        )
        print(f"📝 Blog post created at: {post_path}")
        
    except Exception as e:
        print(f"❌ Blog publishing failed: {e}")
        print("🔄 All changes were automatically rolled back!")


def demo_order_processing():
    """Demonstrate the order processing workflow."""
    print("\n🎯 DEMO: E-commerce Order Processing")
    print("=" * 50)
    
    # Set up some test inventory
    conn = sqlite3.connect("ecommerce.db")
    conn.execute('''CREATE TABLE IF NOT EXISTS inventory 
                   (sku TEXT PRIMARY KEY, name TEXT, price REAL, stock INTEGER)''')
    
    # Insert test products
    test_products = [
        ('BOOK001', 'Python Programming Guide', 29.99, 10),
        ('BOOK002', 'Web Development Handbook', 34.99, 5),
        ('TECH001', 'Wireless Mouse', 19.99, 20)
    ]
    
    for sku, name, price, stock in test_products:
        conn.execute(
            "INSERT OR REPLACE INTO inventory (sku, name, price, stock) VALUES (?, ?, ?, ?)",
            (sku, name, price, stock)
        )
    conn.commit()
    conn.close()
    
    try:
        # Process a valid order
        order_id = process_customer_order(
            customer_id=12345,
            items=[
                {'sku': 'BOOK001', 'quantity': 2},
                {'sku': 'TECH001', 'quantity': 1}
            ],
            payment_info={'card_number': '1234-5678-9012-3456'}
        )
        print(f"🛒 Order processed successfully: {order_id}")
        
    except Exception as e:
        print(f"❌ Order processing failed: {e}")
        print("🔄 Inventory and payment changes were automatically rolled back!")


def demo_failed_transaction():
    """Demonstrate automatic rollback on failure."""
    print("\n🎯 DEMO: Automatic Rollback on Failure")
    print("=" * 50)
    
    try:
        # This will fail due to invalid card number
        process_customer_order(
            customer_id=99999,
            items=[{'sku': 'BOOK001', 'quantity': 1}],
            payment_info={'card_number': '0000'}  # Invalid card
        )
        
    except Exception as e:
        print(f"❌ Order failed as expected: {e}")
        print("✅ All database and file changes were automatically rolled back!")
        print("💡 The inventory was not modified despite the order attempt!")


if __name__ == "__main__":
    print("🚀 WORKFLOW DECORATOR USAGE EXAMPLES")
    print("=" * 60)
    print("Demonstrating how existing code becomes transactional with decorators")
    print("=" * 60)
    
    # Run demonstrations
    demo_blog_publishing()
    demo_order_processing()
    demo_failed_transaction()
    
    print("\n" + "=" * 60)
    print("🎉 All demonstrations completed!")
    print("💡 Notice how existing code required NO changes except adding decorators!")
    print("=" * 60)