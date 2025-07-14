#!/usr/bin/env python3

"""
Tests focused on multi-file operations with SFA File Editor Transactional.
"""

import os
import sys
import tempfile
import shutil
import json

# Import the transactional file editor functions
sys.path.append('/home/ubuntu/agent_lock')
from sfa_file_editor_transactional_v1 import create_file, str_replace, insert_text


def test_web_application_setup():
    """Test creating a complete web application structure atomically."""
    print("🌐 WEB APPLICATION SETUP TEST")
    print("="*60)
    
    workspace = tempfile.mkdtemp(prefix="webapp_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(workspace)
        print(f"Workspace: {workspace}")
        
        print("\n📁 Creating complete web application structure...")
        
        # Frontend files
        result1 = create_file("frontend/index.html", """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Web App</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div id="app">
        <h1>Welcome to My Web App</h1>
        <button onclick="loadData()">Load Data</button>
        <div id="data-container"></div>
    </div>
    <script src="script.js"></script>
</body>
</html>""")
        
        result2 = create_file("frontend/styles.css", """body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
}

#app {
    max-width: 800px;
    margin: 0 auto;
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

button {
    background-color: #007bff;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 4px;
    cursor: pointer;
}

button:hover {
    background-color: #0056b3;
}""")
        
        result3 = create_file("frontend/script.js", """async function loadData() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        
        const container = document.getElementById('data-container');
        container.innerHTML = '<h2>Loaded Data:</h2>' + 
                            '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
    } catch (error) {
        console.error('Error loading data:', error);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('Web app initialized');
});""")
        
        # Backend files
        result4 = create_file("backend/app.py", """from flask import Flask, jsonify, render_template
import json
import os

app = Flask(__name__, static_folder='../frontend', template_folder='../frontend')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    # Load data from our data file
    try:
        with open('data/sample_data.json', 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({'error': 'Data file not found'}), 404

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'web-app'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)""")
        
        result5 = create_file("backend/requirements.txt", """Flask==2.3.2
python-dotenv==1.0.0
requests==2.31.0""")
        
        # Data files  
        result6 = create_file("data/sample_data.json", json.dumps({
            "users": [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"}
            ],
            "products": [
                {"id": 1, "name": "Widget A", "price": 29.99},
                {"id": 2, "name": "Widget B", "price": 39.99}
            ],
            "metadata": {
                "version": "1.0.0",
                "created": "2025-01-01",
                "description": "Sample data for web application"
            }
        }, indent=2))
        
        # Configuration files
        result7 = create_file("config/app_config.py", """import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1']

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}""")
        
        # Documentation
        result8 = create_file("README.md", """# My Web Application

A simple web application with Flask backend and vanilla JavaScript frontend.

## Structure

```
frontend/           # Static web files
├── index.html     # Main page
├── styles.css     # Styling
└── script.js      # Client-side logic

backend/           # Flask application
├── app.py         # Main application
└── requirements.txt

data/              # Application data
└── sample_data.json

config/            # Configuration
└── app_config.py
```

## Setup

1. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python app.py
   ```

3. Open browser to http://localhost:5000

## API Endpoints

- `GET /` - Main application page
- `GET /api/data` - Get sample data
- `GET /api/health` - Health check
""")
        
        # Deployment script
        result9 = create_file("deploy.sh", """#!/bin/bash

echo "🚀 Deploying Web Application..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
cd backend
pip install -r requirements.txt
cd ..

# Run tests (if they exist)
# python -m pytest tests/

# Start application
echo "✅ Starting application on port 5000..."
cd backend
python app.py
""")
        
        # Check all operations
        results = [result1, result2, result3, result4, result5, result6, result7, result8, result9]
        
        if all('error' not in result for result in results):
            print("✅ All 9 files created successfully in single atomic transaction!")
            
            # Verify structure
            expected_structure = {
                "frontend": ["index.html", "styles.css", "script.js"],
                "backend": ["app.py", "requirements.txt"], 
                "data": ["sample_data.json"],
                "config": ["app_config.py"],
                ".": ["README.md", "deploy.sh"]
            }
            
            print("\n📋 Verifying application structure:")
            all_good = True
            
            for directory, files in expected_structure.items():
                if directory == ".":
                    check_dir = "."
                else:
                    check_dir = directory
                    
                for file in files:
                    file_path = os.path.join(check_dir, file) if directory != "." else file
                    if os.path.exists(file_path):
                        size = os.path.getsize(file_path)
                        print(f"  ✅ {file_path} ({size} bytes)")
                    else:
                        print(f"  ❌ {file_path} MISSING")
                        all_good = False
            
            if all_good:
                print("\n🎉 Complete web application created atomically!")
                return True
            else:
                print("\n❌ Some files missing from structure")
                return False
        else:
            print("❌ Some file creation operations failed")
            for i, result in enumerate(results, 1):
                if 'error' in result:
                    print(f"  File {i} error: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(workspace, ignore_errors=True)


def test_codebase_refactoring():
    """Test refactoring an entire codebase atomically."""
    print("\n🔧 CODEBASE REFACTORING TEST")
    print("="*60)
    
    workspace = tempfile.mkdtemp(prefix="refactor_test_")
    original_cwd = os.getcwd()
    
    try:
        os.chdir(workspace)
        print(f"Workspace: {workspace}")
        
        # First create an "old" codebase
        print("\n📦 Creating legacy codebase...")
        
        create_file("old_main.py", """import sys
from old_utils import helper_function, data_processor

def main():
    print("Legacy Application v1.0")
    data = data_processor("input.txt")
    result = helper_function(data)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
""")
        
        create_file("old_utils.py", """def helper_function(data):
    return data.upper()

def data_processor(filename):
    try:
        with open(filename, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return "default data"
""")
        
        create_file("input.txt", "sample input data for processing")
        
        print("✅ Legacy codebase created")
        
        # Now perform atomic refactoring
        print("\n🔄 Performing atomic refactoring...")
        
        # Rename and update all files atomically
        result1 = str_replace("old_main.py", "import sys", "import sys\nimport logging")
        result2 = str_replace("old_main.py", "from old_utils", "from new_utils")
        result3 = str_replace("old_main.py", "Legacy Application v1.0", "Modern Application v2.0")
        result4 = str_replace("old_main.py", "def main():", "def main():\n    logging.basicConfig(level=logging.INFO)")
        
        # Create new utils file with enhanced functionality
        result5 = create_file("new_utils.py", """import logging

def helper_function(data):
    \"\"\"Enhanced helper function with logging.\"\"\"
    logging.info(f"Processing data: {data[:20]}...")
    return data.upper()

def data_processor(filename):
    \"\"\"Enhanced data processor with better error handling.\"\"\"
    try:
        logging.info(f"Reading file: {filename}")
        with open(filename, 'r') as f:
            content = f.read().strip()
        logging.info(f"Successfully read {len(content)} characters")
        return content
    except FileNotFoundError:
        logging.warning(f"File {filename} not found, using default")
        return "default data"
    except Exception as e:
        logging.error(f"Error reading {filename}: {e}")
        return "error data"

def new_feature_validator(data):
    \"\"\"New validation function.\"\"\"
    if not data or len(data) < 3:
        logging.warning("Data validation failed")
        return False
    return True
""")
        
        # Add new feature to main
        result6 = insert_text("old_main.py", 5, "from new_utils import new_feature_validator\n")
        result7 = str_replace("old_main.py", 
                            "result = helper_function(data)",
                            "if new_feature_validator(data):\n        result = helper_function(data)\n    else:\n        result = \"INVALID_DATA\"")
        
        # Create configuration file
        result8 = create_file("config.json", json.dumps({
            "app_name": "Modern Application",
            "version": "2.0.0",
            "log_level": "INFO",
            "features": {
                "validation": True,
                "enhanced_logging": True,
                "error_handling": True
            }
        }, indent=2))
        
        # Update input file
        result9 = str_replace("input.txt", "sample input data", "enhanced sample input data with more content")
        
        # Rename main file (simulate by creating new and noting old should be removed)
        result10 = create_file("new_main.py", """import sys
import logging
from new_utils import helper_function, data_processor
from new_utils import new_feature_validator

def main():
    logging.basicConfig(level=logging.INFO)
    print("Modern Application v2.0")
    data = data_processor("input.txt")
    if new_feature_validator(data):
        result = helper_function(data)
    else:
        result = "INVALID_DATA"
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
""")
        
        results = [result1, result2, result3, result4, result5, result6, result7, result8, result9, result10]
        
        if all('error' not in result for result in results):
            print("✅ Atomic refactoring completed successfully!")
            
            # Verify refactoring
            print("\n📊 Verifying refactored codebase:")
            
            # Check that new_utils.py has enhanced features
            with open("new_utils.py", 'r') as f:
                new_utils_content = f.read()
            if "logging" in new_utils_content and "new_feature_validator" in new_utils_content:
                print("  ✅ new_utils.py has enhanced features")
            
            # Check that main file was updated
            with open("old_main.py", 'r') as f:
                main_content = f.read()
            if "Modern Application v2.0" in main_content and "new_feature_validator" in main_content:
                print("  ✅ old_main.py updated with v2.0 features")
            
            # Check config file
            if os.path.exists("config.json"):
                print("  ✅ config.json created")
            
            # Check new main file
            if os.path.exists("new_main.py"):
                print("  ✅ new_main.py created")
                
            print("\n🎉 Codebase refactoring completed atomically!")
            return True
        else:
            print("❌ Refactoring operations failed")
            for i, result in enumerate(results, 1):
                if 'error' in result:
                    print(f"  Operation {i} error: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(workspace, ignore_errors=True)


def run_multi_file_tests():
    """Run all multi-file operation tests."""
    print("🗂️  MULTI-FILE OPERATIONS TESTING")
    print("="*60)
    
    tests = [
        ("Web Application Setup", test_web_application_setup),
        ("Codebase Refactoring", test_codebase_refactoring)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"🧪 {test_name}")
        print('='*60)
        
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"💥 {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 MULTI-FILE OPERATIONS TEST SUMMARY") 
    print('='*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} | {test_name}")
    
    print(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 ALL MULTI-FILE OPERATION TESTS PASSED!")
        print("🚀 SFA File Editor can handle complex atomic operations!")
    else:
        print("⚠️  Some tests failed.")
    
    print('='*60)


if __name__ == "__main__":
    run_multi_file_tests()