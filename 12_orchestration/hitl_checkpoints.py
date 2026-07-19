"""
Level 47: Human-in-the-Loop — Checkpoints and Handoffs

Uses Strands' built-in handoff_to_user tool from strands_tools.

Two modes (from strands_tools/handoff_to_user.py source):

  breakout_of_loop=False  → synchronous checkpoint
                            agent pauses, calls get_user_input(), waits for
                            typed response, receives it, continues

  breakout_of_loop=True   → terminal handoff
                            sets request_state["stop_event_loop"] = True
                            agent terminates gracefully after displaying message

The agent decides WHEN to call handoff_to_user based on its own assessment.
No external policy engine — the LLM calls the tool when it judges that human
input is appropriate (confidence-based routing pattern, Orkes 2025).

Depends on: L23 (Error Recovery), L22 (Safety)
Sources: strands_tools/handoff_to_user.py, Anthropic Building Effective Agents,
         Orkes HITL, Deloitte AI Agent Orchestration 2026

Scenario: expense report approval agent
  < $100       → auto-approve (no checkpoint, agent continues)
  $100–$999    → Mode 1: pause, request human approval, continue
  ≥ $1000      → Mode 1: pause, require human authorisation, continue
  end of batch → Mode 2: terminal handoff with summary, stop
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands_tools import handoff_to_user

from tools import get_model

# ---------------------------------------------------------------------------
# Expense items — mix of auto-approve, checkpoint, and high-value escalation
# ---------------------------------------------------------------------------
EXPENSE_ITEMS = [
    {"id": "E001", "description": "Team lunch",                    "amount":    45.00, "category": "meals"},
    {"id": "E002", "description": "Software license renewal",      "amount":   299.00, "category": "software"},
    {"id": "E003", "description": "Conference attendance fee",      "amount":  1850.00, "category": "travel"},
    {"id": "E004", "description": "Office supplies",               "amount":    23.50, "category": "supplies"},
    {"id": "E005", "description": "Cloud infrastructure overage",  "amount":  4200.00, "category": "infrastructure"},
]

SYSTEM_PROMPT = """You are an expense approval agent. Review each expense item and apply this policy:

POLICY:
- Amount < $100:      auto-approve immediately, no human review needed
- Amount $100–$999:   call handoff_to_user (breakout_of_loop=False) to request
                      human approval. State the item and amount clearly. Ask for
                      yes/no. Wait for response. If "yes" → approve. If "no" → reject.
- Amount ≥ $1000:     call handoff_to_user (breakout_of_loop=False) to escalate
                      for human authorisation. These require explicit sign-off.
                      Wait for response before recording decision.

FINAL STEP: After processing ALL items, call handoff_to_user (breakout_of_loop=True)
with a concise summary table of all decisions (item ID, amount, decision).
This terminates your session.

Keep messages to the human brief and actionable."""


def main() -> None:
    if not sys.stdin.isatty():
        print("Note: this level requires an interactive terminal.")
        print("Run directly: uv run python 12_orchestration/hitl_checkpoints.py")
        print()
        print("In a real terminal the agent pauses at checkpoints and waits")
        print("for your typed input before continuing.")
        print()

    model = get_model("haiku")

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[handoff_to_user],
    )

    items_text = "\n".join(
        f"  {item['id']}: {item['description']} — ${item['amount']:.2f} ({item['category']})"
        for item in EXPENSE_ITEMS
    )

    print("=" * 60)
    print("Level 47: Human-in-the-Loop — Checkpoints and Handoffs")
    print("=" * 60)
    print()
    print("Expense items to process:")
    for item in EXPENSE_ITEMS:
        tier = (
            "auto-approve"
            if item["amount"] < 100
            else "checkpoint" if item["amount"] < 1000
            else "escalate"
        )
        print(f"  {item['id']}  ${item['amount']:>8.2f}  {item['description']:<35}  [{tier}]")
    print()
    print("Modes in use:")
    print("  breakout_of_loop=False  →  agent pauses, waits for input, continues")
    print("  breakout_of_loop=True   →  agent terminates, hands off to human")
    print("=" * 60)
    print()

    agent(
        f"Please process this expense report batch:\n\n{items_text}\n\n"
        "Apply the approval policy to each item in order. "
        "After all items are processed, hand off with the final summary."
    )

    print()
    print("Session ended — control returned to caller.")


if __name__ == "__main__":
    main()
