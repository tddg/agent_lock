#!/usr/bin/env python3

"""
Test that writelines method works correctly in TransactionalFile.
"""

import os
import tempfile
import shutil
from tx_auto_integrated import transactional


@transactional
def test_writelines_operation():
    """Test writelines method in transactional context."""
    print("Testing writelines method...")
    
    lines = [
        "Line 1\n",
        "Line 2\n", 
        "Line 3\n"
    ]
    
    with open("test_writelines.txt", "w") as f:
        f.writelines(lines)
    
    print("✓ writelines completed successfully")


def verify_writelines_fix():
    """Verify the writelines fix works."""
    print("=" * 50)
    print("TESTING WRITELINES FIX")
    print("=" * 50)
    
    # Cleanup
    if os.path.exists("test_writelines.txt"):
        os.remove("test_writelines.txt")
    
    try:
        test_writelines_operation()
        
        # Verify file was created with correct content
        if os.path.exists("test_writelines.txt"):
            with open("test_writelines.txt", "r") as f:
                content = f.read()
            
            expected = "Line 1\nLine 2\nLine 3\n"
            if content == expected:
                print("✓ File content matches expected output")
                print("✓ writelines method working correctly")
            else:
                print(f"✗ Content mismatch:")
                print(f"  Expected: {repr(expected)}")
                print(f"  Actual: {repr(content)}")
        else:
            print("✗ File was not created")
            
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        if os.path.exists("test_writelines.txt"):
            os.remove("test_writelines.txt")
    
    print("=" * 50)
    print("WRITELINES FIX VERIFICATION COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    verify_writelines_fix()