#!/usr/bin/env python3

"""
Test suite for workflow-aware decorators.

Demonstrates how existing code can be made transactional with minimal changes.
"""

import asyncio
import os
import sqlite3
import tempfile
import shutil
from pathlib import Path

from workflow_decorators import auto_transactional, workflow_atomic, transactional


def test_basic_decorator():
    """Test basic decorator functionality with file operations."""
    print("\n🧪 TEST: Basic Decorator Functionality")
    print("-" * 50)
    
    test_dir = tempfile.mkdtemp(prefix="decorator_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        @auto_transactional(debug=True)
        def create_simple_file():
            # This is regular code that gets automatically transactional
            with open("simple.txt", "w") as f:
                f.write("Hello from decorator!")
            return "simple.txt"
        
        # Execute function
        result = create_simple_file()
        
        # Verify file was created
        assert os.path.exists("simple.txt"), "File should be created"
        with open("simple.txt", "r") as f:
            content = f.read()
            assert "Hello from decorator!" in content, "Content should match"
        
        print("✅ Basic decorator test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def test_rollback_on_failure():
    """Test automatic rollback when function fails."""
    print("\n🧪 TEST: Automatic Rollback on Failure")
    print("-" * 50)
    
    test_dir = tempfile.mkdtemp(prefix="rollback_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        @auto_transactional(debug=True)
        def failing_function():
            # Create a file
            with open("will_be_rolled_back.txt", "w") as f:
                f.write("This file should not exist after rollback")
            
            # Then fail
            raise ValueError("Intentional failure for testing")
        
        # Execute function and expect failure
        try:
            failing_function()
            print("❌ Function should have failed")
            return False
        except Exception as e:
            print(f"✅ Expected failure occurred: {type(e).__name__}")
        
        # Verify file was rolled back (should not exist)
        file_exists = os.path.exists("will_be_rolled_back.txt")
        if file_exists:
            print("❌ File should have been rolled back but still exists")
            return False
        else:
            print("✅ File was successfully rolled back")
        
        print("✅ Rollback test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def test_database_operations():
    """Test decorator with database operations."""
    print("\n🧪 TEST: Database Operations")
    print("-" * 50)
    
    test_dir = tempfile.mkdtemp(prefix="db_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        @auto_transactional(debug=True, track_operations=["database"])
        def create_database_records():
            # Create database and table
            conn = sqlite3.connect("test.db")
            conn.execute('''CREATE TABLE IF NOT EXISTS users 
                           (id INTEGER PRIMARY KEY, name TEXT, email TEXT)''')
            
            # Insert records
            conn.execute("INSERT INTO users (name, email) VALUES (?, ?)", 
                        ("John Doe", "john@example.com"))
            conn.execute("INSERT INTO users (name, email) VALUES (?, ?)", 
                        ("Jane Smith", "jane@example.com"))
            
            conn.commit()
            conn.close()
            
            return "test.db"
        
        # Execute function
        result = create_database_records()
        
        # Verify database was created and has records
        assert os.path.exists("test.db"), "Database file should exist"
        
        conn = sqlite3.connect("test.db")
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        conn.close()
        
        assert count == 2, f"Should have 2 users, but found {count}"
        
        print("✅ Database operations test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def test_mixed_operations():
    """Test decorator with both file and database operations."""
    print("\n🧪 TEST: Mixed File and Database Operations")
    print("-" * 50)
    
    test_dir = tempfile.mkdtemp(prefix="mixed_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        @auto_transactional(debug=True, track_operations=["all"])
        def create_blog_post():
            # This simulates a typical blog post creation workflow
            post_title = "My First Post"
            post_content = "This is the content of my first blog post."
            
            # Create the blog post file
            post_file = "posts/first-post.md"
            os.makedirs("posts", exist_ok=True)
            
            with open(post_file, "w") as f:
                f.write(f"# {post_title}\n\n{post_content}")
            
            # Update database with post metadata
            conn = sqlite3.connect("blog.db")
            conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                           (id INTEGER PRIMARY KEY, title TEXT, file_path TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            conn.execute("INSERT INTO posts (title, file_path) VALUES (?, ?)", 
                        (post_title, post_file))
            
            conn.commit()
            conn.close()
            
            # Create an index file
            with open("index.html", "w") as f:
                f.write(f"<html><body><h1>Latest Post: {post_title}</h1></body></html>")
            
            return post_file
        
        # Execute function
        result = create_blog_post()
        
        # Verify all operations completed
        assert os.path.exists("posts/first-post.md"), "Blog post file should exist"
        assert os.path.exists("blog.db"), "Database should exist"
        assert os.path.exists("index.html"), "Index file should exist"
        
        # Verify database content
        conn = sqlite3.connect("blog.db")
        cursor = conn.execute("SELECT title, file_path FROM posts WHERE title = ?", ("My First Post",))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None, "Database record should exist"
        assert row[0] == "My First Post", "Title should match"
        assert row[1] == "posts/first-post.md", "File path should match"
        
        print("✅ Mixed operations test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def test_mixed_operations_with_failure():
    """Test rollback with mixed operations when function fails."""
    print("\n🧪 TEST: Mixed Operations with Rollback")
    print("-" * 50)
    
    test_dir = tempfile.mkdtemp(prefix="mixed_rollback_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        @auto_transactional(debug=True, track_operations=["all"])
        def failing_blog_post():
            # Create some files and database records, then fail
            post_title = "Failed Post"
            
            # Create the blog post file
            with open("failed-post.md", "w") as f:
                f.write(f"# {post_title}\n\nThis should be rolled back.")
            
            # Update database
            conn = sqlite3.connect("blog.db")
            conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                           (id INTEGER PRIMARY KEY, title TEXT, file_path TEXT)''')
            conn.execute("INSERT INTO posts (title, file_path) VALUES (?, ?)", 
                        (post_title, "failed-post.md"))
            conn.commit()
            conn.close()
            
            # Create another file
            with open("also-should-be-rolled-back.txt", "w") as f:
                f.write("This file should not exist after rollback")
            
            # Now fail intentionally
            raise RuntimeError("Blog post creation failed!")
        
        # Execute function and expect failure
        try:
            failing_blog_post()
            print("❌ Function should have failed")
            return False
        except Exception as e:
            print(f"✅ Expected failure occurred: {type(e).__name__}")
        
        # Verify all files and database records were rolled back
        files_exist = [
            os.path.exists("failed-post.md"),
            os.path.exists("blog.db"),
            os.path.exists("also-should-be-rolled-back.txt")
        ]
        
        if any(files_exist):
            print(f"❌ Some files still exist after rollback: {files_exist}")
            return False
        else:
            print("✅ All files and database records were successfully rolled back")
        
        print("✅ Mixed operations rollback test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


async def test_async_function():
    """Test decorator with async functions."""
    print("\n🧪 TEST: Async Function Support")
    print("-" * 50)
    
    test_dir = tempfile.mkdtemp(prefix="async_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        @auto_transactional(debug=True)
        async def async_file_creation():
            # Simulate async work
            await asyncio.sleep(0.1)
            
            # Create file
            with open("async-file.txt", "w") as f:
                f.write("Created by async function!")
            
            await asyncio.sleep(0.1)
            return "async-file.txt"
        
        # Execute async function
        result = await async_file_creation()
        
        # Verify file was created
        assert os.path.exists("async-file.txt"), "Async file should exist"
        with open("async-file.txt", "r") as f:
            content = f.read()
            assert "async function" in content, "Content should match"
        
        print("✅ Async function test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def test_convenience_aliases():
    """Test convenience alias decorators."""
    print("\n🧪 TEST: Convenience Aliases")
    print("-" * 50)
    
    test_dir = tempfile.mkdtemp(prefix="alias_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        
        @workflow_atomic(debug=True)
        def test_workflow_atomic():
            with open("atomic.txt", "w") as f:
                f.write("Created with workflow_atomic")
            return "atomic.txt"
        
        @transactional(debug=True)
        def test_transactional():
            with open("transactional.txt", "w") as f:
                f.write("Created with transactional")
            return "transactional.txt"
        
        # Test both aliases
        result1 = test_workflow_atomic()
        result2 = test_transactional()
        
        # Verify both work
        assert os.path.exists("atomic.txt"), "workflow_atomic should work"
        assert os.path.exists("transactional.txt"), "transactional should work"
        
        print("✅ Convenience aliases test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


async def run_all_decorator_tests():
    """Run all decorator tests."""
    print("🧪 WORKFLOW DECORATOR TESTS")
    print("=" * 60)
    print("Testing workflow-aware decorators for easy integration")
    print("=" * 60)
    
    tests = [
        ("Basic Decorator Functionality", test_basic_decorator()),
        ("Automatic Rollback on Failure", test_rollback_on_failure()),
        ("Database Operations", test_database_operations()),
        ("Mixed File and Database Operations", test_mixed_operations()),
        ("Mixed Operations with Rollback", test_mixed_operations_with_failure()),
        ("Async Function Support", test_async_function()),
        ("Convenience Aliases", test_convenience_aliases())
    ]
    
    results = {}
    
    for test_name, test_coro in tests:
        print(f"\n{'='*60}")
        print(f"RUNNING: {test_name}")
        print('='*60)
        
        try:
            if asyncio.iscoroutine(test_coro):
                result = await test_coro
            else:
                result = test_coro
            results[test_name] = result
        except Exception as e:
            print(f"💥 {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 WORKFLOW DECORATOR TEST RESULTS")
    print('='*60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} | {test_name}")
    
    print(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 ALL WORKFLOW DECORATOR TESTS PASSED!")
        print("🚀 Decorators make existing code automatically transactional!")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    print('='*60)


if __name__ == "__main__":
    asyncio.run(run_all_decorator_tests())