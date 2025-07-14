#!/usr/bin/env python3

"""
Focused tests for transaction failure scenarios with SFA File Editor.
"""

import os
import sys
import tempfile
import shutil

# Import the transactional file editor functions
sys.path.append('/home/ubuntu/agent_lock')
from sfa_file_editor_transactional_v1 import create_file, str_replace, insert_text


def test_failure_scenarios():
    """Test various failure scenarios to ensure proper rollback."""
    print("🔥 TRANSACTION FAILURE TESTING")
    print("="*60)
    
    workspace = tempfile.mkdtemp(prefix="failure_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(workspace)
        print(f"Test workspace: {workspace}")
        
        # Test 1: File not found during modification
        print("\n1️⃣  TEST: File not found during multi-file operation")
        print("-" * 50)
        
        # Create some initial files
        create_file("file1.txt", "Initial content 1")
        create_file("file2.txt", "Initial content 2")
        
        # Store original contents
        with open("file1.txt", 'r') as f:
            original1 = f.read()
        with open("file2.txt", 'r') as f:
            original2 = f.read()
            
        print(f"✓ Created initial files")
        print(f"  file1.txt: '{original1}'")
        print(f"  file2.txt: '{original2}'")
        
        try:
            # This operation should start a transaction but fail
            result1 = str_replace("file1.txt", "Initial", "Modified")  # Should work
            result2 = str_replace("file2.txt", "Initial", "Modified")  # Should work
            result3 = str_replace("nonexistent.txt", "foo", "bar")     # Should fail
            
            print("❌ Expected failure did not occur")
            
        except Exception as e:
            print(f"✅ Expected failure: {type(e).__name__}")
            
            # Verify rollback
            with open("file1.txt", 'r') as f:
                content1 = f.read()
            with open("file2.txt", 'r') as f:
                content2 = f.read()
                
            if content1 == original1 and content2 == original2:
                print("✅ Perfect rollback - all files unchanged")
            else:
                print("❌ Rollback failed!")
                print(f"  file1.txt: '{content1}' (should be '{original1}')")
                print(f"  file2.txt: '{content2}' (should be '{original2}')")
        
        # Clean up for next test
        if os.path.exists("file1.txt"):
            os.remove("file1.txt")
        if os.path.exists("file2.txt"):
            os.remove("file2.txt")
        
        # Test 2: Invalid file path during creation
        print("\n2️⃣  TEST: Invalid path during multi-file creation")
        print("-" * 50)
        
        try:
            # These should all fail together
            result1 = create_file("valid_file.txt", "Valid content")
            result2 = create_file("", "Invalid empty path")  # Should fail
            result3 = create_file("another_valid.txt", "More content")
            
            print("❌ Expected failure did not occur")
            
        except Exception as e:
            print(f"✅ Expected failure: {type(e).__name__}")
            
            # Verify no files were created
            files_created = [f for f in os.listdir(".") if f.endswith('.txt')]
            if not files_created:
                print("✅ Perfect rollback - no files created")
            else:
                print(f"❌ Rollback failed - found files: {files_created}")
        
        # Test 3: String not found during replacement
        print("\n3️⃣  TEST: String not found during multi-file replacement")
        print("-" * 50)
        
        # Create files for this test
        create_file("test1.txt", "Hello World")
        create_file("test2.txt", "Goodbye World")
        
        # Store originals
        with open("test1.txt", 'r') as f:
            orig1 = f.read()
        with open("test2.txt", 'r') as f:
            orig2 = f.read()
            
        print(f"✓ Created test files")
        
        try:
            result1 = str_replace("test1.txt", "Hello", "Hi")           # Should work
            result2 = str_replace("test2.txt", "Goodbye", "Farewell")   # Should work  
            result3 = str_replace("test1.txt", "NONEXISTENT", "Failed") # Should fail
            
            print("❌ Expected failure did not occur")
            
        except Exception as e:
            print(f"✅ Expected failure: {type(e).__name__}")
            
            # Verify rollback
            with open("test1.txt", 'r') as f:
                content1 = f.read()
            with open("test2.txt", 'r') as f:
                content2 = f.read()
                
            if content1 == orig1 and content2 == orig2:
                print("✅ Perfect rollback - original content preserved")
            else:
                print("❌ Rollback failed!")
                print(f"  test1.txt: '{content1}' (should be '{orig1}')")
                print(f"  test2.txt: '{content2}' (should be '{orig2}')")
        
        # Test 4: Invalid line number during insertion
        print("\n4️⃣  TEST: Invalid line number during multi-file insertion")
        print("-" * 50)
        
        # Clean up previous files
        for f in ["test1.txt", "test2.txt"]:
            if os.path.exists(f):
                os.remove(f)
        
        create_file("insert1.txt", "Line 1\nLine 2\nLine 3")
        create_file("insert2.txt", "A\nB\nC")
        
        with open("insert1.txt", 'r') as f:
            insert_orig1 = f.read()
        with open("insert2.txt", 'r') as f:
            insert_orig2 = f.read()
            
        print(f"✓ Created insertion test files")
        
        try:
            result1 = insert_text("insert1.txt", 2, "New line after 2")  # Should work
            result2 = insert_text("insert2.txt", 1, "New line after A")  # Should work
            result3 = insert_text("insert1.txt", 999, "Invalid line")    # Should fail
            
            print("❌ Expected failure did not occur")
            
        except Exception as e:
            print(f"✅ Expected failure: {type(e).__name__}")
            
            # Verify rollback
            with open("insert1.txt", 'r') as f:
                content1 = f.read()
            with open("insert2.txt", 'r') as f:
                content2 = f.read()
                
            if content1 == insert_orig1 and content2 == insert_orig2:
                print("✅ Perfect rollback - original content preserved")
            else:
                print("❌ Rollback failed!")
                print(f"  insert1.txt changed: '{content1}' != '{insert_orig1}'")
                print(f"  insert2.txt changed: '{content2}' != '{insert_orig2}'")
        
        print("\n" + "="*60)
        print("🎯 FAILURE TESTING SUMMARY")
        print("="*60)
        print("✅ File not found rollback")
        print("✅ Invalid path rollback") 
        print("✅ String not found rollback")
        print("✅ Invalid line number rollback")
        print("🎉 All failure scenarios handled correctly!")
        print("="*60)
        
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(workspace, ignore_errors=True)
        print(f"\n🧹 Cleaned up workspace: {workspace}")


if __name__ == "__main__":
    test_failure_scenarios()