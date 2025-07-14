#!/usr/bin/env python3

import asyncio
import tempfile
from pathlib import Path
import shutil

from tx_mini import Transaction, Op
from adaptors import FileSystemAdaptor


async def test_simple():
    """Simple test to debug the issue."""
    temp_dir = tempfile.mkdtemp()
    print(f"Using temp dir: {temp_dir}")
    
    try:
        adaptor = FileSystemAdaptor(temp_dir)
        op = Op("fs.write", {"path": "test.txt", "data": "Hello, World!"})
        
        print("1. Creating operation...")
        print(f"   Op ID: {op.op_id}")
        
        print("2. Executing do()...")
        await adaptor.do(op)
        
        target_path = Path(temp_dir) / "test.txt"
        print(f"3. Target file exists after do(): {target_path.exists()}")
        print(f"   Temp files: {adaptor.temp_files}")
        
        print("4. Executing undo()...")
        await adaptor.undo(op)
        
        print(f"5. Target file exists after undo(): {target_path.exists()}")
        print(f"   Temp files: {adaptor.temp_files}")
        
        if target_path.exists():
            print(f"   File content: {target_path.read_text()}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(test_simple())