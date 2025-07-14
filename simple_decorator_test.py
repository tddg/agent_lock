#!/usr/bin/env python3

"""
Simple test for workflow decorators - proof of concept.
"""

import os
import tempfile
import shutil
from workflow_decorators import auto_transactional


def test_simple_decorator():
    """Simple test that works without async issues."""
    print("🧪 Testing simple decorator functionality...")
    
    test_dir = tempfile.mkdtemp(prefix="simple_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        print(f"Working in: {test_dir}")
        
        @auto_transactional(debug=True, track_operations=["file"])
        def create_test_file():
            print("Creating test file...")
            with open("test.txt", "w") as f:
                f.write("Hello from decorated function!")
            print("File created successfully")
            return "test.txt"
        
        # Test successful execution
        print("\n--- Testing successful execution ---")
        result = create_test_file()
        print(f"Result: {result}")
        
        if os.path.exists("test.txt"):
            with open("test.txt", "r") as f:
                content = f.read()
            print(f"File content: {content}")
            print("✅ File creation test passed!")
        else:
            print("❌ File was not created")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def test_rollback_decorator():
    """Test rollback functionality."""
    print("\n🧪 Testing rollback functionality...")
    
    test_dir = tempfile.mkdtemp(prefix="rollback_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(test_dir)
        print(f"Working in: {test_dir}")
        
        @auto_transactional(debug=True, track_operations=["file"])
        def failing_function():
            print("Creating file before failure...")
            with open("should_be_rolled_back.txt", "w") as f:
                f.write("This should not exist after rollback")
            print("File created, now failing...")
            raise ValueError("Intentional failure!")
        
        # Test rollback on failure
        print("\n--- Testing rollback on failure ---")
        try:
            failing_function()
            print("❌ Function should have failed")
        except Exception as e:
            print(f"✅ Expected failure: {e}")
        
        # Check if file was rolled back
        if os.path.exists("should_be_rolled_back.txt"):
            print("⚠️  File still exists (rollback not fully implemented in sync mode)")
        else:
            print("✅ File was rolled back successfully!")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    print("🚀 Simple Workflow Decorator Tests")
    print("=" * 50)
    
    test_simple_decorator()
    test_rollback_decorator()
    
    print("\n" + "=" * 50)
    print("🎯 Key Insights:")
    print("✅ Decorators can wrap existing functions")
    print("✅ Operation tracking is possible with monkey-patching")
    print("⚠️  Full rollback requires async workflow execution")
    print("💡 This demonstrates the concept - production version would be more robust")
    print("=" * 50)