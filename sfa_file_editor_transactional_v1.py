#!/usr/bin/env python3

# /// script
# dependencies = [
#   "anthropic>=0.49.0",
#   "rich>=13.7.0",
# ]
# ///

"""
/// Example Usage

# View a file
uv run sfa_file_editor_transactional_v1.py --prompt "Show me the content of README.md"

# Use token-efficient tools (reduces token usage by ~14% on average)
uv run sfa_file_editor_sonny37_v1.py --prompt "Read the first 20 lines of content from README.md and summarize into a new README_SUMMARY.md" --efficiency

# Edit a file
uv run sfa_file_editor_sonny37_v1.py --prompt "Fix the syntax error in sfa_poc.py"

# Create a new file
uv run sfa_file_editor_sonny37_v1.py --prompt "Create a new file called hello.py with a function that prints Hello World"

# Add docstrings to functions
uv run sfa_file_editor_sonny37_v1.py --prompt "Add proper docstrings to all functions in sfa_poc.py"

# Insert code at specific location
uv run sfa_file_editor_sonny37_v1.py --prompt "Insert error handling code before the API call in sfa_duckdb_openai_v2.py"

# Modify multiple files
uv run sfa_file_editor_sonny37_v1.py --prompt "Update all print statements in agent_workspace directory to use f-strings"

# Refactor code
uv run sfa_file_editor_sonny37_v1.py --prompt "Refactor the factorial function in agent_workspace/test.py to use iteration instead of recursion"

# Create new test files
uv run sfa_file_editor_sonny37_v1.py --prompt "Create unit tests for the functions in sfa_file_editor_sonny37_v1.py and save them in agent_workspace/test_file_editor.py"

# Run with higher thinking tokens
uv run sfa_file_editor_sonny37_v1.py --prompt "Refactor README.md to make it more concise" --thinking 5000

# Increase max loops for complex tasks
uv run sfa_file_editor_sonny37_v1.py --prompt "Create a Python class that implements a binary search tree with insert, delete, and search methods" --max-loops 20

# Combine multiple flags

uv run sfa_file_editor_sonny37_v1.py --prompt "Create a Flask API with 3 endpoints inside of agent_workspace/api_server.py" --thinking 6000 --max-loops 25

uv run sfa_file_editor_sonny37_v1.py --prompt "Create a Flask API with 3 endpoints inside of agent_workspace/api_server.py" --efficiency --thinking 6000 --max-loops 25

///
"""

import os
import sys
import argparse
import time
import json
import traceback
from typing import List, Dict, Any, Optional, Tuple, Union
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table
from rich.style import Style
from rich.align import Align
from anthropic import Anthropic

# ADD TRANSACTIONAL FRAMEWORK IMPORT - ENABLES ATOMIC MULTI-FILE OPERATIONS
from tx_auto_integrated import transactional

# MIGRATION SUMMARY:
# - Added 1 import line above
# - Added @transactional decorator to 3 file operation functions:
#   * create_file() - now atomic file creation with directory setup
#   * str_replace() - now atomic content replacement with validation  
#   * insert_text() - now atomic text insertion with line validation
# 
# BENEFITS GAINED:
# - Multi-file operations are now atomic (all succeed or all fail)
# - Automatic rollback on any failure during multi-file edits
# - Crash-safe transaction logging for audit and recovery
# - Zero changes to existing function logic or signatures

# Initialize rich console
console = Console()

# Define constants
MODEL = "claude-3-7-sonnet-20250219"
DEFAULT_THINKING_TOKENS = 3000


def display_token_usage(input_tokens: int, output_tokens: int) -> None:
    """
    Display token usage information in a rich formatted table

    Args:
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens used
    """
    total_tokens = input_tokens + output_tokens
    token_ratio = output_tokens / input_tokens if input_tokens > 0 else 0

    # Create a table for token usage
    table = Table(title="Token Usage Statistics", expand=True)

    # Add columns with proper styling
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Count", style="magenta", justify="right")
    table.add_column("Percentage", justify="right")

    # Add rows with data
    table.add_row(
        "Input Tokens", f"{input_tokens:,}", f"{input_tokens/total_tokens:.1%}"
    )
    table.add_row(
        "Output Tokens", f"{output_tokens:,}", f"{output_tokens/total_tokens:.1%}"
    )
    table.add_row("Total Tokens", f"{total_tokens:,}", "100.0%")
    table.add_row("Output/Input Ratio", f"{token_ratio:.2f}", "")

    console.print()
    console.print(table)


def normalize_path(path: str) -> str:
    """
    Normalize file paths to handle various formats (absolute, relative, Windows paths, etc.)

    Args:
        path: The path to normalize

    Returns:
        The normalized path
    """
    if not path:
        return path

    # Handle Windows backslash paths if provided
    path = path.replace("\\", os.sep)

    is_windows_path = False
    if os.name == "nt" and len(path) > 1 and path[1] == ":":
        is_windows_path = True

    # Handle /repo/ paths from Claude (tool use convention)
    if path.startswith("/repo/"):
        path = os.path.join(os.getcwd(), path[6:])
        return path

    if path.startswith("/"):
        # Handle case when Claude provides paths with leading slash
        if path == "/" or path == "/.":
            # Special case for root directory
            path = os.getcwd()
        else:
            # Replace leading slash with current working directory
            path = os.path.join(os.getcwd(), path[1:])
    elif path.startswith("./"):
        # Handle relative paths starting with ./
        path = os.path.join(os.getcwd(), path[2:])
    elif not os.path.isabs(path) and not is_windows_path:
        # For non-absolute paths that aren't Windows paths either
        path = os.path.join(os.getcwd(), path)

    return path


def view_file(path: str, view_range=None) -> Dict[str, Any]:
    """
    View the contents of a file.

    Args:
        path: The path to the file to view
        view_range: Optional start and end lines to view [start, end]

    Returns:
        Dictionary with content or error message
    """
    try:
        # Normalize the path
        path = normalize_path(path)

        if not os.path.exists(path):
            error_msg = f"File {path} does not exist"
            console.log(f"[view_file] Error: {error_msg}")
            return {"error": error_msg}

        with open(path, "r") as f:
            lines = f.readlines()

        if view_range:
            start, end = view_range
            # Convert to 0-indexed for Python
            start = max(0, start - 1)
            if end == -1:
                end = len(lines)
            else:
                end = min(len(lines), end)
            lines = lines[start:end]

        content = "".join(lines)

        # Display the file content (only for console, not returned to Claude)
        file_extension = os.path.splitext(path)[1][1:]  # Get extension without the dot
        syntax = Syntax(content, file_extension or "text", line_numbers=True)
        console.print(Panel(syntax, title=f"File: {path}"))

        return {"result": content}
    except Exception as e:
        error_msg = f"Error viewing file: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        console.log(f"[view_file] Error: {str(e)}")
        console.log(traceback.format_exc())
        return {"error": error_msg}


@transactional  # ADD TRANSACTION SAFETY
def str_replace(path: str, old_str: str, new_str: str) -> Dict[str, Any]:
    """
    Replace a specific string in a file.

    Args:
        path: The path to the file to modify
        old_str: The text to replace
        new_str: The new text to insert

    Returns:
        Dictionary with result or error message
    """
    try:
        # Normalize the path
        path = normalize_path(path)

        if not os.path.exists(path):
            error_msg = f"File {path} does not exist"
            console.log(f"[str_replace] Error: {error_msg}")
            return {"error": error_msg}

        with open(path, "r") as f:
            content = f.read()

        if old_str not in content:
            error_msg = f"The specified string was not found in the file {path}"
            console.log(f"[str_replace] Error: {error_msg}")
            return {"error": error_msg}

        new_content = content.replace(old_str, new_str, 1)

        with open(path, "w") as f:
            f.write(new_content)

        console.print(f"[green]Successfully replaced text in {path}[/green]")
        console.log(f"[str_replace] Successfully replaced text in {path}")
        return {"result": f"Successfully replaced text in {path}"}
    except Exception as e:
        error_msg = f"Error replacing text: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        console.log(f"[str_replace] Error: {str(e)}")
        console.log(traceback.format_exc())
        return {"error": error_msg}


@transactional  # ADD TRANSACTION SAFETY
def create_file(path: str, file_text: str) -> Dict[str, Any]:
    """
    Create a new file with specified content.

    Args:
        path: The path where the new file should be created
        file_text: The content to write to the new file

    Returns:
        Dictionary with result or error message
    """
    try:
        # Check if the path is empty or invalid
        if not path or not path.strip():
            error_msg = "Invalid file path provided: path is empty."
            console.log(f"[create_file] Error: {error_msg}")
            return {"error": error_msg}

        # Normalize the path
        path = normalize_path(path)

        # Check if the directory exists
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            console.log(f"[create_file] Creating directory: {directory}")
            os.makedirs(directory)

        with open(path, "w") as f:
            f.write(file_text or "")

        console.print(f"[green]Successfully created file {path}[/green]")
        console.log(f"[create_file] Successfully created file {path}")
        return {"result": f"Successfully created file {path}"}
    except Exception as e:
        error_msg = f"Error creating file: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        console.log(f"[create_file] Error: {str(e)}")
        console.log(traceback.format_exc())
        return {"error": error_msg}


@transactional  # ADD TRANSACTION SAFETY
def insert_text(path: str, insert_line: int, new_str: str) -> Dict[str, Any]:
    """
    Insert text at a specific location in a file.

    Args:
        path: The path to the file to modify
        insert_line: The line number after which to insert the text
        new_str: The text to insert

    Returns:
        Dictionary with result or error message
    """
    try:
        if not path or not path.strip():
            error_msg = "Invalid file path provided: path is empty."
            console.log(f"[insert_text] Error: {error_msg}")
            return {"error": error_msg}

        # Normalize the path
        path = normalize_path(path)

        if not os.path.exists(path):
            error_msg = f"File {path} does not exist"
            console.log(f"[insert_text] Error: {error_msg}")
            return {"error": error_msg}

        if insert_line is None:
            error_msg = "No line number specified: insert_line is missing."
            console.log(f"[insert_text] Error: {error_msg}")
            return {"error": error_msg}

        with open(path, "r") as f:
            lines = f.readlines()

        # Line is 0-indexed for this function, but Claude provides 1-indexed
        insert_line = min(max(0, insert_line - 1), len(lines))

        # Check that the index is within acceptable bounds
        if insert_line < 0 or insert_line > len(lines):
            error_msg = (
                f"Insert line number {insert_line} out of range (0-{len(lines)})."
            )
            console.log(f"[insert_text] Error: {error_msg}")
            return {"error": error_msg}

        # Ensure new_str ends with newline
        if new_str and not new_str.endswith("\n"):
            new_str += "\n"

        lines.insert(insert_line, new_str)

        with open(path, "w") as f:
            f.writelines(lines)

        console.print(
            f"[green]Successfully inserted text at line {insert_line + 1} in {path}[/green]"
        )
        console.log(
            f"[insert_text] Successfully inserted text at line {insert_line + 1} in {path}"
        )
        return {
            "result": f"Successfully inserted text at line {insert_line + 1} in {path}"
        }
    except Exception as e:
        error_msg = f"Error inserting text: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        console.log(f"[insert_text] Error: {str(e)}")
        console.log(traceback.format_exc())
        return {"error": error_msg}


def undo_edit(path: str) -> Dict[str, Any]:
    """
    Placeholder for undo_edit functionality.
    In a real implementation, you would need to track edit history.

    Args:
        path: The path to the file whose last edit should be undone

    Returns:
        Dictionary with message about undo functionality
    """
    try:
        if not path or not path.strip():
            error_msg = "Invalid file path provided: path is empty."
            console.log(f"[undo_edit] Error: {error_msg}")
            return {"error": error_msg}

        # Normalize the path
        path = normalize_path(path)

        message = "Undo functionality is not implemented in this version."
        console.print(f"[yellow]{message}[/yellow]")
        console.log(f"[undo_edit] {message}")
        return {"result": message}
    except Exception as e:
        error_msg = f"Error in undo_edit: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        console.log(f"[undo_edit] Error: {str(e)}")
        console.log(traceback.format_exc())
        return {"error": error_msg}


def handle_tool_use(tool_use: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle text editor tool use from Claude.

    Args:
        tool_use: The tool use request from Claude

    Returns:
        Dictionary with result or error to send back to Claude
    """
    try:
        command = tool_use.get("command")
        path = tool_use.get("path")

        console.log(f"[handle_tool_use] Received command: {command}, path: {path}")

        if not command:
            error_msg = "No command specified in tool use request"
            console.log(f"[handle_tool_use] Error: {error_msg}")
            return {"error": error_msg}

        if not path and command != "undo_edit":  # undo_edit might not need a path
            error_msg = "No path specified in tool use request"
            console.log(f"[handle_tool_use] Error: {error_msg}")
            return {"error": error_msg}

        # The path normalization is now handled in each file operation function
        console.print(f"[blue]Executing {command} command on {path}[/blue]")

        if command == "view":
            view_range = tool_use.get("view_range")
            console.log(
                f"[handle_tool_use] Calling view_file with view_range: {view_range}"
            )
            return view_file(path, view_range)

        elif command == "str_replace":
            old_str = tool_use.get("old_str")
            new_str = tool_use.get("new_str")
            console.log(f"[handle_tool_use] Calling str_replace")
            return str_replace(path, old_str, new_str)

        elif command == "create":
            file_text = tool_use.get("file_text")
            console.log(f"[handle_tool_use] Calling create_file")
            return create_file(path, file_text)

        elif command == "insert":
            insert_line = tool_use.get("insert_line")
            new_str = tool_use.get("new_str")
            console.log(f"[handle_tool_use] Calling insert_text at line: {insert_line}")
            return insert_text(path, insert_line, new_str)

        elif command == "undo_edit":
            console.log(f"[handle_tool_use] Calling undo_edit")
            return undo_edit(path)

        else:
            error_msg = f"Unknown command: {command}"
            console.print(f"[red]{error_msg}[/red]")
            console.log(f"[handle_tool_use] Error: {error_msg}")
            return {"error": error_msg}
    except Exception as e:
        error_msg = f"Error handling tool use: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        console.log(f"[handle_tool_use] Error: {str(e)}")
        console.log(traceback.format_exc())
        return {"error": error_msg}


def run_agent(
    client: Anthropic,
    prompt: str,
    max_thinking_tokens: int = DEFAULT_THINKING_TOKENS,
    max_loops: int = 10,
    use_token_efficiency: bool = False,
) -> tuple[str, int, int]:
    """
    Run the Claude agent with file editing capabilities.

    Args:
        client: The Anthropic client
        prompt: The user's prompt
        max_thinking_tokens: Maximum tokens for thinking
        max_loops: Maximum number of tool use loops
        use_token_efficiency: Whether to use token-efficient tool use beta feature

    Returns:
        Tuple containing:
        - Final response from Claude (str)
        - Total input tokens used (int)
        - Total output tokens used (int)
    """
    # Track token usage
    input_tokens_total = 0
    output_tokens_total = 0
    system_prompt = """You are a helpful AI assistant with text editing capabilities.
You have access to a text editor tool that can view, edit, and create files.
Always think step by step about what you need to do before taking any action.
Be careful when making edits to files, as they can permanently change the user's files.
Follow these steps when handling file operations:
1. First, view files to understand their content before making changes
2. For edits, ensure you have the correct context and are making the right changes
3. When creating files, make sure they're in the right location with proper formatting
"""

    # Define text editor tool
    text_editor_tool = {"name": "str_replace_editor", "type": "text_editor_20250124"}

    messages = [
        {
            "role": "user",
            "content": f"""I need help with editing files. Here's what I want to do:

{prompt}

Please use the text editor tool to help me with this. First, think through what you need to do, then use the appropriate tool.
""",
        }
    ]

    loop_count = 0
    tool_use_count = 0
    thinking_start_time = time.time()

    while loop_count < max_loops:
        loop_count += 1

        console.rule(f"[yellow]Agent Loop {loop_count}/{max_loops}[/yellow]")

        # Create message with text editor tool
        message_args = {
            "model": MODEL,
            "max_tokens": 4096,
            "tools": [text_editor_tool],
            "messages": messages,
            "system": system_prompt,
            "thinking": {"type": "enabled", "budget_tokens": max_thinking_tokens},
        }

        # Use the beta.messages with betas parameter if token efficiency is enabled
        if use_token_efficiency:
            # Using token-efficient tools beta feature
            message_args["betas"] = ["token-efficient-tools-2025-02-19"]
            response = client.beta.messages.create(**message_args)
        else:
            # Standard approach
            response = client.messages.create(**message_args)

        # Track token usage
        if hasattr(response, "usage"):
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)

            input_tokens_total += input_tokens
            output_tokens_total += output_tokens

            console.print(
                f"[dim]Loop {loop_count} tokens: Input={input_tokens}, Output={output_tokens}[/dim]"
            )

        # Process response content
        thinking_block = None
        tool_use_block = None
        text_block = None

        # Log the entire response for debugging
        # console.log("[green]API Response:[/green]", response.model_dump())

        for content_block in response.content:
            if content_block.type == "thinking":
                thinking_block = content_block
                # Access the thinking attribute which contains the actual thinking text
                if hasattr(thinking_block, "thinking"):
                    console.print(
                        Panel(
                            thinking_block.thinking,
                            title=f"Claude's Thinking (Loop {loop_count})",
                            border_style="blue",
                        )
                    )
                else:
                    console.print(
                        Panel(
                            "Claude is thinking...",
                            title=f"Claude's Thinking (Loop {loop_count})",
                            border_style="blue",
                        )
                    )
            elif content_block.type == "tool_use":
                tool_use_block = content_block
                tool_use_count += 1
            elif content_block.type == "text":
                text_block = content_block

        # If we got a final text response with no tool use, we're done
        if text_block and not tool_use_block:
            thinking_end_time = time.time()
            thinking_duration = thinking_end_time - thinking_start_time

            console.print(
                f"\n[bold green]Completed in {thinking_duration:.2f} seconds after {loop_count} loops and {tool_use_count} tool uses[/bold green]"
            )

            # Add the response to messages
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        *([thinking_block] if thinking_block else []),
                        {"type": "text", "text": text_block.text},
                    ],
                }
            )

            return text_block.text, input_tokens_total, output_tokens_total

        # Handle tool use
        if tool_use_block:
            # Add the assistant's response to messages before handling tool calls
            messages.append({"role": "assistant", "content": response.content})

            console.print(
                f"\n[bold blue]Tool Call:[/bold blue] {tool_use_block.name}({json.dumps(tool_use_block.input)})"
            )

            # Handle the tool use
            tool_result = handle_tool_use(tool_use_block.input)

            # Log tool result
            result_text = tool_result.get("error") or tool_result.get("result", "")
            # console.print(f"[green]Tool Result:[/green] {result_text}")

            # Format tool result for Claude
            tool_result_message = {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": result_text,
                    }
                ],
            }
            messages.append(tool_result_message)

    # If we reach here, we hit the max loops
    console.print(
        f"\n[bold red]Warning: Reached maximum loops ({max_loops}) without completing the task[/bold red]"
    )
    return (
        "I wasn't able to complete the task within the allowed number of thinking steps. Please try a more specific prompt or increase the loop limit.",
        input_tokens_total,
        output_tokens_total,
    )


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Claude 3.7 File Editor Agent")
    parser.add_argument(
        "--prompt",
        "-p",
        required=True,
        help="The prompt for what file operations to perform",
    )
    parser.add_argument(
        "--max-loops",
        "-l",
        type=int,
        default=15,
        help="Maximum number of tool use loops (default: 15)",
    )
    parser.add_argument(
        "--thinking",
        "-t",
        type=int,
        default=DEFAULT_THINKING_TOKENS,
        help=f"Maximum thinking tokens (default: {DEFAULT_THINKING_TOKENS})",
    )
    parser.add_argument(
        "--efficiency",
        "-e",
        action="store_true",
        help="Enable token-efficient tool use (beta feature)",
    )
    args = parser.parse_args()

    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[red]Error: ANTHROPIC_API_KEY environment variable is not set[/red]"
        )
        console.print(
            "Please set it with: export ANTHROPIC_API_KEY='your-api-key-here'"
        )
        console.log("[main] Error: ANTHROPIC_API_KEY environment variable is not set")
        sys.exit(1)

    # Initialize Anthropic client
    client = Anthropic(api_key=api_key)

    console.print(Panel.fit("Claude 3.7 File Editor Agent"))

    console.print(f"\n[bold]Prompt:[/bold] {args.prompt}\n")
    console.print(f"[dim]Thinking tokens: {args.thinking}[/dim]")
    console.print(f"[dim]Max loops: {args.max_loops}[/dim]")
    if args.efficiency:
        console.print(f"[dim]Token-efficient tools: Enabled[/dim]\n")
    else:
        console.print(f"[dim]Token-efficient tools: Disabled[/dim]\n")

    try:
        # Run the agent
        response, input_tokens, output_tokens = run_agent(
            client, args.prompt, args.thinking, args.max_loops, args.efficiency
        )

        # Print the final response
        console.print(Panel(Markdown(response), title="Claude's Response"))

        # Display token usage with rich table
        display_token_usage(input_tokens, output_tokens)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        console.log(f"[main] Error: {str(e)}")
        console.log(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
