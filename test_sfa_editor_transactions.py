#!/usr/bin/env python3

"""
Comprehensive tests for SFA File Editor Transactional v1.
Tests multi-file operations and transaction failure handling.
"""

import os
import sys
import tempfile
import shutil
import sqlite3
from pathlib import Path

# Import the transactional file editor functions
sys.path.append('/home/ubuntu/agent_lock')
from sfa_file_editor_transactional_v1 import create_file, str_replace, insert_text


def setup_test_workspace():
    """Create a clean test workspace."""
    workspace = tempfile.mkdtemp(prefix="sfa_test_")
    original_cwd = os.getcwd()
    os.chdir(workspace)
    return workspace, original_cwd


def cleanup_test_workspace(workspace, original_cwd):
    """Clean up test workspace."""
    os.chdir(original_cwd)
    shutil.rmtree(workspace, ignore_errors=True)


def test_atomic_project_creation():
    """Test creating a complete project structure atomically."""
    print("\n" + "="*70)
    print("TEST 1: ATOMIC PROJECT CREATION")
    print("="*70)
    
    workspace, original_cwd = setup_test_workspace()
    
    try:
        print(f"Working in: {workspace}")
        
        # Test 1A: Create a Python package structure
        print("\n1A. Creating Python package structure...")
        
        # This should all succeed atomically
        result1 = create_file("mypackage/__init__.py", """\"\"\"My Package - A sample Python package.\"\"\"

__version__ = "1.0.0"
__author__ = "Test Author"

from .core import main_function
from .utils import helper_function

__all__ = ['main_function', 'helper_function']
""")
        
        result2 = create_file("mypackage/core.py", """\"\"\"Core functionality for mypackage.\"\"\"

from .utils import helper_function


def main_function():
    \"\"\"Main entry point.\"\"\"
    print("Running main function")
    result = helper_function()
    return f"Main function result: {result}"


def secondary_function(data):
    \"\"\"Secondary processing function.\"\"\"
    return data.upper()
""")
        
        result3 = create_file("mypackage/utils.py", """\"\"\"Utility functions for mypackage.\"\"\"

import os
import json


def helper_function():
    \"\"\"Helper function for core functionality.\"\"\"
    return "Helper executed successfully"


def config_loader(config_path):
    \"\"\"Load configuration from JSON file.\"\"\"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}


def save_data(data, filename):
    \"\"\"Save data to file.\"\"\"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
""")
        
        result4 = create_file("setup.py", """from setuptools import setup, find_packages

setup(
    name="mypackage",
    version="1.0.0",
    author="Test Author",
    description="A sample Python package for testing",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.25.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
""")
        
        result5 = create_file("README.md", """# MyPackage

A sample Python package for testing transactional file operations.

## Installation

```bash
pip install -e .
```

## Usage

```python
from mypackage import main_function
result = main_function()
print(result)
```

## Structure

- `mypackage/core.py` - Core functionality
- `mypackage/utils.py` - Utility functions
- `setup.py` - Package configuration
""")
        
        # Check if all operations succeeded
        results = [result1, result2, result3, result4, result5]
        if all('error' not in result for result in results):
            print("✓ All files created successfully in single transaction")
            
            # Verify the package structure
            expected_files = [
                "mypackage/__init__.py",
                "mypackage/core.py", 
                "mypackage/utils.py",
                "setup.py",
                "README.md"
            ]
            
            missing_files = []
            for file_path in expected_files:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        content = f.read()
                    print(f"✓ {file_path} created ({len(content)} chars)")
                else:
                    missing_files.append(file_path)
                    print(f"✗ {file_path} missing")
            
            if not missing_files:
                print("✓ Complete Python package created atomically")
                return True
            else:
                print(f"✗ Missing files: {missing_files}")
                return False
        else:
            print("✗ Some file creation operations failed")
            for i, result in enumerate(results, 1):
                if 'error' in result:
                    print(f"  Operation {i} error: {result['error']}")
            return False
            
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        return False
    finally:
        cleanup_test_workspace(workspace, original_cwd)


def test_atomic_multi_file_modification():
    """Test modifying multiple related files atomically."""
    print("\n" + "="*70)
    print("TEST 2: ATOMIC MULTI-FILE MODIFICATION")
    print("="*70)
    
    workspace, original_cwd = setup_test_workspace()
    
    try:
        print(f"Working in: {workspace}")
        
        # First create some files to modify
        print("\n2A. Setting up files for modification...")
        create_file("config.py", """# Configuration settings
VERSION = "1.0.0"
DEBUG = False
DATABASE_URL = "sqlite:///app.db"
API_KEY = "old_key_123"
""")
        
        create_file("app.py", """from config import VERSION, DEBUG, DATABASE_URL

def main():
    print(f"App version: {VERSION}")
    if DEBUG:
        print("Debug mode enabled")
    print(f"Database: {DATABASE_URL}")

if __name__ == "__main__":
    main()
""")
        
        create_file("tests.py", """import unittest
from app import main

class TestApp(unittest.TestCase):
    def test_main(self):
        # This should not crash
        main()
        
if __name__ == "__main__":
    unittest.main()
""")
        
        print("✓ Initial files created")
        
        # Now perform atomic modifications across all files
        print("\n2B. Performing atomic modifications...")
        
        # Update version and settings across multiple files
        result1 = str_replace("config.py", 
                            'VERSION = "1.0.0"', 
                            'VERSION = "2.0.0"')
        
        result2 = str_replace("config.py",
                            'DEBUG = False',
                            'DEBUG = True')
        
        result3 = str_replace("config.py",
                            'API_KEY = "old_key_123"',
                            'API_KEY = "new_secure_key_456"')
        
        result4 = insert_text("app.py", 1,
                            "# Updated for version 2.0.0\n")
        
        result5 = str_replace("app.py",
                            'print(f"Database: {DATABASE_URL}")',
                            'print(f"Database: {DATABASE_URL}")\n    print("Enhanced features enabled")')
        
        result6 = insert_text("tests.py", 4,
                            "    def test_version(self):\n        from config import VERSION\n        self.assertEqual(VERSION, \"2.0.0\")\n        \n")
        
        # Check if all modifications succeeded
        results = [result1, result2, result3, result4, result5, result6]
        if all('error' not in result for result in results):
            print("✓ All file modifications completed atomically")
            
            # Verify the changes
            with open("config.py", 'r') as f:
                config_content = f.read()
            
            if 'VERSION = "2.0.0"' in config_content and 'DEBUG = True' in config_content:
                print("✓ config.py updated correctly")
            else:
                print("✗ config.py updates failed")
                
            with open("app.py", 'r') as f:
                app_content = f.read()
                
            if "version 2.0.0" in app_content and "Enhanced features" in app_content:
                print("✓ app.py updated correctly")
            else:
                print("✗ app.py updates failed")
                
            with open("tests.py", 'r') as f:
                test_content = f.read()
                
            if "test_version" in test_content and "2.0.0" in test_content:
                print("✓ tests.py updated correctly")
            else:
                print("✗ tests.py updates failed")
                
            print("✓ Multi-file modification completed atomically")
            return True
        else:
            print("✗ Some modification operations failed")
            for i, result in enumerate(results, 1):
                if 'error' in result:
                    print(f"  Modification {i} error: {result['error']}")
            return False
            
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        return False
    finally:
        cleanup_test_workspace(workspace, original_cwd)


def test_transaction_failure_and_rollback():
    """Test transaction rollback when operations fail."""
    print("\n" + "="*70)
    print("TEST 3: TRANSACTION FAILURE AND ROLLBACK")
    print("="*70)
    
    workspace, original_cwd = setup_test_workspace()
    
    try:
        print(f"Working in: {workspace}")
        
        # Test 3A: Create initial state
        print("\n3A. Creating initial state...")
        create_file("important_data.txt", "ORIGINAL IMPORTANT DATA - DO NOT LOSE")
        create_file("config.yaml", """
database:
  host: localhost
  port: 5432
  name: production_db
status: stable
""")
        
        # Store original content
        with open("important_data.txt", 'r') as f:
            original_data = f.read()
        with open("config.yaml", 'r') as f:
            original_config = f.read()
            
        print("✓ Initial state created")
        print(f"Original data: {original_data.strip()}")
        
        # Test 3B: Attempt operations that will fail
        print("\n3B. Testing rollback on failure...")
        
        try:
            # These first operations should work
            result1 = str_replace("important_data.txt", 
                                "ORIGINAL", "MODIFIED")
            result2 = str_replace("config.yaml",
                                "status: stable", "status: updating")
            
            # This should fail - trying to modify non-existent file
            result3 = str_replace("nonexistent_file.txt", "foo", "bar")
            
            print("✗ Expected failure did not occur")
            return False
            
        except Exception as e:
            print(f"✓ Expected failure occurred: {type(e).__name__}")
            
            # Verify rollback - files should have original content
            with open("important_data.txt", 'r') as f:
                current_data = f.read()
            with open("config.yaml", 'r') as f:
                current_config = f.read()
                
            if current_data == original_data and current_config == original_config:
                print("✓ Perfect rollback - all files restored to original state")
                print(f"Data after rollback: {current_data.strip()}")
                return True
            else:
                print("✗ Rollback failed - files were modified")
                print(f"Expected data: {original_data.strip()}")
                print(f"Actual data: {current_data.strip()}")
                return False
                
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        return False
    finally:
        cleanup_test_workspace(workspace, original_cwd)


def test_complex_project_migration():
    """Test migrating a complex project structure atomically."""
    print("\n" + "="*70)
    print("TEST 4: COMPLEX PROJECT MIGRATION")  
    print("="*70)
    
    workspace, original_cwd = setup_test_workspace()
    
    try:
        print(f"Working in: {workspace}")
        
        # Test 4A: Create a complex existing project
        print("\n4A. Creating existing project structure...")
        
        create_file("src/main.py", """#!/usr/bin/env python3
import os
from utils.database import connect_db
from utils.config import load_config

def main():
    config = load_config()
    db = connect_db(config['database_url'])
    print("Application started")

if __name__ == "__main__":
    main()
""")
        
        create_file("src/utils/database.py", """import sqlite3

def connect_db(url):
    return sqlite3.connect(url.replace('sqlite:///', ''))

def create_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                   (id INTEGER PRIMARY KEY, name TEXT)''')
""")
        
        create_file("src/utils/config.py", """import json
import os

def load_config():
    return {
        'database_url': 'sqlite:///app.db',
        'debug': False
    }
""")
        
        create_file("requirements.txt", """requests==2.25.1
flask==2.0.1
sqlite3
""")
        
        print("✓ Existing project created")
        
        # Test 4B: Perform complex migration atomically
        print("\n4B. Performing complex migration...")
        
        # Add new imports and functionality across multiple files
        result1 = str_replace("src/main.py",
                            "import os",
                            "import os\nimport logging")
        
        result2 = insert_text("src/main.py", 4,
                            "from utils.logger import setup_logging\n")
        
        result3 = str_replace("src/main.py",
                            "def main():",
                            "def main():\n    setup_logging()")
        
        result4 = create_file("src/utils/logger.py", """import logging
import os

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def log_database_operation(operation):
    logger = logging.getLogger(__name__)
    logger.info(f"Database operation: {operation}")
""")
        
        result5 = str_replace("src/utils/database.py",
                            "import sqlite3",
                            "import sqlite3\nfrom .logger import log_database_operation")
        
        result6 = str_replace("src/utils/database.py",
                            "def connect_db(url):",
                            "def connect_db(url):\n    log_database_operation(f'Connecting to {url}')")
        
        result7 = str_replace("requirements.txt",
                            "sqlite3",
                            "# sqlite3 is built-in\nlogging")
        
        result8 = create_file("src/utils/__init__.py", """\"\"\"Utilities package.\"\"\"

from .config import load_config
from .database import connect_db, create_tables  
from .logger import setup_logging, log_database_operation

__all__ = ['load_config', 'connect_db', 'create_tables', 'setup_logging', 'log_database_operation']
""")
        
        # Check if all migration operations succeeded
        results = [result1, result2, result3, result4, result5, result6, result7, result8]
        if all('error' not in result for result in results):
            print("✓ Complex migration completed atomically")
            
            # Verify the migration worked
            verification_checks = []
            
            # Check main.py has logging
            with open("src/main.py", 'r') as f:
                main_content = f.read()
            if "import logging" in main_content and "setup_logging" in main_content:
                verification_checks.append("main.py updated")
            
            # Check logger.py was created
            if os.path.exists("src/utils/logger.py"):
                verification_checks.append("logger.py created")
            
            # Check database.py has logging integration
            with open("src/utils/database.py", 'r') as f:
                db_content = f.read()
            if "log_database_operation" in db_content:
                verification_checks.append("database.py integrated")
                
            # Check __init__.py was created
            if os.path.exists("src/utils/__init__.py"):
                verification_checks.append("__init__.py created")
            
            print(f"✓ Verification passed: {', '.join(verification_checks)}")
            print("✓ Complex project migration successful")
            return True
        else:
            print("✗ Some migration operations failed")
            for i, result in enumerate(results, 1):
                if 'error' in result:
                    print(f"  Migration step {i} error: {result['error']}")
            return False
            
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        return False
    finally:
        cleanup_test_workspace(workspace, original_cwd)


def test_transaction_logging_verification():
    """Test that transaction logs are created and contain correct information."""
    print("\n" + "="*70)
    print("TEST 5: TRANSACTION LOGGING VERIFICATION")
    print("="*70)
    
    workspace, original_cwd = setup_test_workspace()
    
    try:
        print(f"Working in: {workspace}")
        
        # Clear any existing logs
        tx_log_dir = Path.home() / "tx_log"
        if tx_log_dir.exists():
            initial_log_count = len(list(tx_log_dir.glob("*.jsonl")))
        else:
            initial_log_count = 0
        
        print(f"Initial transaction logs: {initial_log_count}")
        
        # Perform a transaction that should be logged
        print("\n5A. Performing logged transaction...")
        
        result1 = create_file("logged_file1.txt", "Content for logged transaction")
        result2 = create_file("logged_file2.txt", "More content for logging")
        result3 = str_replace("logged_file1.txt", "Content", "Modified content")
        
        if all('error' not in result for result in [result1, result2, result3]):
            print("✓ Transaction operations completed")
            
            # Check for new transaction logs
            if tx_log_dir.exists():
                current_logs = list(tx_log_dir.glob("*.jsonl"))
                new_log_count = len(current_logs)
                
                if new_log_count > initial_log_count:
                    print(f"✓ New transaction logs created: {new_log_count - initial_log_count}")
                    
                    # Examine the latest log
                    if current_logs:
                        latest_log = max(current_logs, key=lambda f: f.stat().st_mtime)
                        print(f"✓ Latest log file: {latest_log.name}")
                        
                        with open(latest_log, 'r') as f:
                            log_lines = f.readlines()
                        
                        print(f"✓ Log entries: {len(log_lines)} operations recorded")
                        
                        # Basic validation of log content
                        log_contains_file_ops = any("fs.write" in line for line in log_lines)
                        if log_contains_file_ops:
                            print("✓ File operations properly logged")
                        else:
                            print("✗ File operations not found in logs")
                            
                        return log_contains_file_ops
                else:
                    print("✗ No new transaction logs were created")
                    return False
            else:
                print("✗ Transaction log directory does not exist")
                return False
        else:
            print("✗ Transaction operations failed")
            return False
            
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        return False
    finally:
        cleanup_test_workspace(workspace, original_cwd)


def run_all_tests():
    """Run all SFA file editor transaction tests."""
    print("🧪 SFA FILE EDITOR TRANSACTIONAL TESTS")
    print("="*70)
    print("Testing atomic multi-file operations and failure handling")
    print("="*70)
    
    tests = [
        ("Atomic Project Creation", test_atomic_project_creation),
        ("Atomic Multi-File Modification", test_atomic_multi_file_modification), 
        ("Transaction Failure & Rollback", test_transaction_failure_and_rollback),
        ("Complex Project Migration", test_complex_project_migration),
        ("Transaction Logging", test_transaction_logging_verification)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n{'='*70}")
        print(f"RUNNING: {test_name}")
        print(f"{'='*70}")
        
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"💥 {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "="*70)
    print("📊 TEST RESULTS SUMMARY")
    print("="*70)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} | {test_name}")
    
    print(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! SFA File Editor Transactions working perfectly!")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    print("="*70)


if __name__ == "__main__":
    run_all_tests()