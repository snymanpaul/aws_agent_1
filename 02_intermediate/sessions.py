"""
Level 5: Sessions & State Management
====================================
Persist agent state and conversation history across interactions.

Key Concepts:
- Session managers persist conversation history
- Agents can remember previous interactions
- State survives script restarts
- FileSessionManager for local storage, S3SessionManager for cloud

Built-in Session Managers:
- FileSessionManager: Local filesystem storage
- S3SessionManager: Amazon S3 bucket storage

Run: uv run python 02_intermediate/sessions.py
"""

import os
import shutil
from strands import Agent
from strands.models.openai import OpenAIModel
from strands.session.file_session_manager import FileSessionManager

# Configure model
model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={
        "base_url": "http://localhost:4000",
        "api_key": "sk-local"
    }
)

# Session storage directory
SESSION_DIR = "./sessions"

print("=" * 70)
print("Level 5: Sessions & State Management")
print("=" * 70)
print()

# =============================================================================
# Example 1: Basic Session Persistence
# =============================================================================

print("Example 1: Basic Session Persistence")
print("-" * 50)
print()

# Create agent with session manager
# session_id identifies the conversation, storage_dir is where files are saved
SESSION_ID = "demo-session-001"

agent_with_memory = Agent(
    model=model,
    session_manager=FileSessionManager(
        session_id=SESSION_ID,
        storage_dir=SESSION_DIR
    ),
    system_prompt="You are a helpful assistant. Remember details the user shares with you."
)

# First interaction - share information
print("Turn 1: Sharing personal info")
print("-" * 30)
agent_with_memory("My name is Paul and I'm learning about AI agents. I work with Kotlin and Python.")
print()

# Second interaction - ask about previous info
print("Turn 2: Testing memory recall")
print("-" * 30)
agent_with_memory("What's my name and what programming languages do I work with?")
print()

# =============================================================================
# Example 2: Session Restoration (Simulating Restart)
# =============================================================================

print("Example 2: Session Restoration (Simulating Restart)")
print("-" * 50)
print()

# Create a NEW agent instance with the SAME session_id
# This simulates what happens when you restart your application
print("Creating new agent instance with same session_id...")
print("(This simulates restarting your application)")
print()

restored_agent = Agent(
    model=model,
    session_manager=FileSessionManager(
        session_id=SESSION_ID,  # Same session ID = restore conversation
        storage_dir=SESSION_DIR
    ),
    system_prompt="You are a helpful assistant. Remember details the user shares with you."
)

print("Turn 3: Testing memory after 'restart'")
print("-" * 30)
restored_agent("Based on our previous conversation, what do you remember about me?")
print()

# =============================================================================
# Example 3: Multiple Independent Sessions
# =============================================================================

print("Example 3: Multiple Independent Sessions")
print("-" * 50)
print()

# User A's session
user_a_agent = Agent(
    model=model,
    session_manager=FileSessionManager(
        session_id="user-alice-session",
        storage_dir=SESSION_DIR
    ),
    system_prompt="You are a helpful assistant."
)

# User B's session
user_b_agent = Agent(
    model=model,
    session_manager=FileSessionManager(
        session_id="user-bob-session",
        storage_dir=SESSION_DIR
    ),
    system_prompt="You are a helpful assistant."
)

print("Alice's session:")
user_a_agent("Remember that my favorite color is blue and I like hiking.")
print()

print("Bob's session:")
user_b_agent("Remember that my favorite color is green and I like chess.")
print()

print("Verifying session isolation - asking each agent:")
print()

print("Alice's agent recalls:")
user_a_agent("What's my favorite color and hobby?")
print()

print("Bob's agent recalls:")
user_b_agent("What's my favorite color and hobby?")
print()

# =============================================================================
# Example 4: Viewing Session Data
# =============================================================================

print("Example 4: Viewing Stored Sessions")
print("-" * 50)
print()

print(f"Sessions stored in: {SESSION_DIR}/")
if os.path.exists(SESSION_DIR):
    for item in os.listdir(SESSION_DIR):
        item_path = os.path.join(SESSION_DIR, item)
        if os.path.isdir(item_path):
            files = os.listdir(item_path)
            print(f"  {item}/ ({len(files)} file(s))")
        else:
            size = os.path.getsize(item_path)
            print(f"  {item} ({size} bytes)")
print()

# =============================================================================
# Cleanup
# =============================================================================

print("=" * 70)
print("Key Takeaways:")
print("- Sessions persist conversation history automatically")
print("- Same session_id = continued conversation")
print("- Different session_id = isolated conversations")
print("- FileSessionManager stores data locally in JSON format")
print("- For production: Use S3SessionManager or AgentCore Memory")
print("=" * 70)
print()

# Clean up session files after demo
print("Cleaning up session files...")
shutil.rmtree(SESSION_DIR, ignore_errors=True)
print("Done.")
