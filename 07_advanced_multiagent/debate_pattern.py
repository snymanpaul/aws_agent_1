"""
Level 18: Debate Pattern
========================
Adversarial agents for better decisions.

Flow: Advocate ↔ Skeptic → Judge (synthesize)

Four Patterns:
1. Basic Debate: Sequential Advocate → Skeptic → Judge
2. Multi-Round: Structured turns with scoring
3. Code Review: Practical example for development workflows
4. Graph Memory: Persist debates to Graphiti for learning

Key Concepts:
- Adversarial dialogue surfaces hidden risks
- Structured opposition prevents groupthink
- Judge synthesizes balanced recommendations

Run: uv run python 07_advanced_multiagent/debate_pattern.py
"""

import sys
import re
import json
from datetime import datetime

sys.path.insert(0, ".")

from strands import Agent
from tools import get_model

# Models: Use same model for all agents to ensure fair debate
debate_model = get_model("claude-sonnet-4")
fast_model = get_model("gemini-flash")  # For cost-effective iterations


# =============================================================================
# Iteration 1: Basic Debate
# =============================================================================
def basic_debate_demo():
    """Simple sequential debate: Advocate → Skeptic → Judge."""
    print("\n" + "=" * 60)
    print("Iteration 1: Basic Debate")
    print("=" * 60)

    # Create specialized agents
    advocate = Agent(
        model=fast_model,
        system_prompt="""You are a Devil's Advocate, but in FAVOR of proposals.
Your job is to argue FOR decisions, finding:
1. Benefits and opportunities
2. Supporting evidence
3. Reasons why it will succeed
4. Positive outcomes

Be passionate but logical. Present 3-5 key points.
Format: Numbered list with brief explanations.""",
        callback_handler=None
    )

    skeptic = Agent(
        model=fast_model,
        system_prompt="""You are a Critical Skeptic.
Your job is to argue AGAINST decisions, finding:
1. Risks and potential failures
2. Hidden costs and downsides
3. What could go wrong
4. Alternative approaches

Be thorough but fair. Present 3-5 key concerns.
Format: Numbered list with brief explanations.""",
        callback_handler=None
    )

    judge = Agent(
        model=fast_model,
        system_prompt="""You are an impartial Judge.
Your job is to synthesize both sides of the debate:
1. Acknowledge valid points from each side
2. Identify the strongest arguments
3. Provide a balanced recommendation
4. Suggest mitigations for key risks

Format:
ADVOCATE'S BEST POINTS: (2-3 key points)
SKEPTIC'S BEST POINTS: (2-3 key concerns)
RECOMMENDATION: (balanced conclusion)
MITIGATIONS: (if proceeding, how to address risks)""",
        callback_handler=None
    )

    # Debate topic
    topic = "Should we migrate our monolithic application to microservices?"
    print(f"\nTopic: {topic}\n")

    # Phase 1: Advocate argues FOR
    print("[Advocate argues FOR]")
    advocate_response = advocate(f"""Argue IN FAVOR of this decision:

{topic}

Present your strongest arguments for why this is a good idea.""")
    advocate_text = str(advocate_response)
    print(f"Advocate:\n{advocate_text}\n")

    # Phase 2: Skeptic argues AGAINST
    print("[Skeptic argues AGAINST]")
    skeptic_response = skeptic(f"""Argue AGAINST this decision:

{topic}

The Advocate argued:
{advocate_text}

Present your strongest concerns and counterarguments.""")
    skeptic_text = str(skeptic_response)
    print(f"Skeptic:\n{skeptic_text}\n")

    # Phase 3: Judge synthesizes
    print("[Judge synthesizes]")
    judge_response = judge(f"""Synthesize this debate and provide a recommendation:

Topic: {topic}

ADVOCATE'S ARGUMENTS:
{advocate_text}

SKEPTIC'S CONCERNS:
{skeptic_text}

Provide a balanced analysis and recommendation.""")
    judge_text = str(judge_response)
    print(f"Judge:\n{judge_text}")

    return {
        "topic": topic,
        "advocate": advocate_text,
        "skeptic": skeptic_text,
        "judge": judge_text
    }


# =============================================================================
# Iteration 2: Multi-Round Debate
# =============================================================================
def parse_score(text: str) -> int:
    """Extract numeric score from response."""
    patterns = [
        r'SCORE:\s*(\d+)',
        r'(\d+)\s*/\s*10',
        r'score[:\s]+(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return min(10, max(1, int(match.group(1))))
    return 5


def multi_round_debate_demo(num_rounds: int = 2):
    """Structured multi-round debate with scoring."""
    print("\n" + "=" * 60)
    print(f"Iteration 2: Multi-Round Debate ({num_rounds} rounds)")
    print("=" * 60)

    advocate = Agent(
        model=fast_model,
        system_prompt="""You are a persuasive Advocate.
In each round, you must:
1. Respond to the Skeptic's latest points
2. Strengthen your core arguments
3. Present new supporting evidence

Be concise but compelling. End with SCORE: [1-10] for your confidence.""",
        callback_handler=None
    )

    skeptic = Agent(
        model=fast_model,
        system_prompt="""You are a rigorous Skeptic.
In each round, you must:
1. Counter the Advocate's latest points
2. Raise new concerns
3. Question assumptions

Be thorough but fair. End with SCORE: [1-10] for your concern level.""",
        callback_handler=None
    )

    judge = Agent(
        model=fast_model,
        system_prompt="""You are the Debate Judge.
After each round, provide:
1. ROUND WINNER: (Advocate/Skeptic/Tie)
2. KEY INSIGHT: (most valuable point made)
3. RUNNING SCORE: Advocate X - Skeptic Y

Be objective. Award points for logic, evidence, and persuasiveness.""",
        callback_handler=None
    )

    # Debate topic
    topic = "Should we adopt AI code assistants (like GitHub Copilot) for our team?"

    print(f"\nTopic: {topic}\n")

    # Track debate history
    history = []
    advocate_score = 0
    skeptic_score = 0

    # Initial positions
    print("[Opening Statements]")
    advocate_response = advocate(f"Give your opening argument FOR: {topic}")
    advocate_text = str(advocate_response)
    print(f"Advocate: {advocate_text[:200]}...")

    skeptic_response = skeptic(f"Give your opening argument AGAINST: {topic}")
    skeptic_text = str(skeptic_response)
    print(f"Skeptic: {skeptic_text[:200]}...")

    # Debate rounds
    for round_num in range(1, num_rounds + 1):
        print(f"\n[Round {round_num}]")

        # Advocate responds
        advocate_response = advocate(f"""Round {round_num}: Respond to the Skeptic's points.

Skeptic's argument:
{skeptic_text}

Strengthen your position and counter their concerns.""")
        advocate_text = str(advocate_response)
        print(f"Advocate: {advocate_text[:200]}...")

        # Skeptic responds
        skeptic_response = skeptic(f"""Round {round_num}: Counter the Advocate's latest points.

Advocate's argument:
{advocate_text}

Raise new concerns and challenge their evidence.""")
        skeptic_text = str(skeptic_response)
        print(f"Skeptic: {skeptic_text[:200]}...")

        # Judge scores the round
        judge_response = judge(f"""Score Round {round_num}:

ADVOCATE said:
{advocate_text}

SKEPTIC said:
{skeptic_text}

Who won this round?""")
        judge_text = str(judge_response)
        print(f"Judge: {judge_text[:200]}...")

        # Track scores
        if "advocate" in judge_text.lower() and "winner" in judge_text.lower():
            advocate_score += 1
        elif "skeptic" in judge_text.lower() and "winner" in judge_text.lower():
            skeptic_score += 1

        history.append({
            "round": round_num,
            "advocate": advocate_text,
            "skeptic": skeptic_text,
            "judge": judge_text
        })

    # Final verdict
    print("\n[Final Verdict]")
    final_judge = judge(f"""Provide final verdict after {num_rounds} rounds.

Topic: {topic}

Running Score: Advocate {advocate_score} - Skeptic {skeptic_score}

Debate history: {len(history)} rounds

Final recommendation:
1. OVERALL WINNER
2. KEY TAKEAWAYS
3. RECOMMENDED ACTION""")
    print(f"Final: {str(final_judge)}")

    return {
        "topic": topic,
        "rounds": num_rounds,
        "history": history,
        "scores": {"advocate": advocate_score, "skeptic": skeptic_score},
        "final_verdict": str(final_judge)
    }


# =============================================================================
# Iteration 3: Code Review Debate
# =============================================================================
def code_review_debate_demo():
    """Apply debate pattern to code review."""
    print("\n" + "=" * 60)
    print("Iteration 3: Code Review Debate")
    print("=" * 60)

    # Code defender (Advocate)
    defender = Agent(
        model=fast_model,
        system_prompt="""You are a Code Defender.
Your job is to argue that code is well-written:
1. Highlight good design decisions
2. Explain why patterns were chosen
3. Point out maintainability benefits
4. Defend edge case handling

Be fair - acknowledge minor issues but argue they're acceptable.""",
        callback_handler=None
    )

    # Code critic (Skeptic)
    critic = Agent(
        model=fast_model,
        system_prompt="""You are a Code Critic.
Your job is to find issues in code:
1. Identify bugs and edge cases
2. Point out maintainability concerns
3. Question design decisions
4. Suggest improvements

Be constructive - explain why issues matter and suggest fixes.""",
        callback_handler=None
    )

    # Code reviewer (Judge)
    reviewer = Agent(
        model=fast_model,
        system_prompt="""You are a Senior Code Reviewer.
Synthesize the debate into an actionable review:

Format:
APPROVE/REQUEST_CHANGES/COMMENT

STRENGTHS: (what's good)
ISSUES: (what needs fixing)
SUGGESTIONS: (nice-to-haves)

VERDICT: (concise recommendation)""",
        callback_handler=None
    )

    # Sample code to review
    code = '''
def process_user_data(user_input: dict) -> dict:
    """Process and validate user data."""
    result = {}

    # Extract fields
    name = user_input.get("name", "")
    email = user_input.get("email", "")
    age = user_input.get("age", 0)

    # Validate
    if len(name) < 2:
        raise ValueError("Name too short")

    if "@" not in email:
        raise ValueError("Invalid email")

    if age < 0 or age > 150:
        raise ValueError("Invalid age")

    # Process
    result["name"] = name.strip().title()
    result["email"] = email.lower()
    result["age"] = int(age)
    result["is_adult"] = age >= 18

    return result
'''

    print(f"\nCode to review:\n```python{code}```\n")

    # Defender argues code is good
    print("[Defender argues code is well-written]")
    defender_response = defender(f"""Defend this code's quality:

```python{code}```

Argue why this is good, maintainable code.""")
    defender_text = str(defender_response)
    print(f"Defender:\n{defender_text}\n")

    # Critic finds issues
    print("[Critic identifies issues]")
    critic_response = critic(f"""Critique this code:

```python{code}```

The Defender argued:
{defender_text}

Find issues and suggest improvements.""")
    critic_text = str(critic_response)
    print(f"Critic:\n{critic_text}\n")

    # Reviewer synthesizes
    print("[Reviewer provides verdict]")
    reviewer_response = reviewer(f"""Provide code review verdict:

CODE:
```python{code}```

DEFENDER SAYS:
{defender_text}

CRITIC SAYS:
{critic_text}

Give your final review decision.""")
    reviewer_text = str(reviewer_response)
    print(f"Reviewer:\n{reviewer_text}")

    return {
        "code": code,
        "defender": defender_text,
        "critic": critic_text,
        "review": reviewer_text
    }


# =============================================================================
# Iteration 4: Graph Memory Integration
# =============================================================================
def graph_memory_debate_demo():
    """Persist debate outcomes to Graphiti for cross-session learning."""
    print("\n" + "=" * 60)
    print("Iteration 4: Graph Memory Integration")
    print("=" * 60)

    # Run a basic debate
    topic = "Should we use TypeScript instead of JavaScript for new projects?"

    advocate = Agent(
        model=fast_model,
        system_prompt="Argue FOR TypeScript adoption. Be concise: 3 key points.",
        callback_handler=None
    )

    skeptic = Agent(
        model=fast_model,
        system_prompt="Argue AGAINST TypeScript. Be concise: 3 key concerns.",
        callback_handler=None
    )

    judge = Agent(
        model=fast_model,
        system_prompt="Synthesize debate. Give: RECOMMENDATION (1 sentence), CONFIDENCE (1-10).",
        callback_handler=None
    )

    print(f"\nTopic: {topic}\n")

    # Quick debate
    advocate_text = str(advocate(f"Argue FOR: {topic}"))
    skeptic_text = str(skeptic(f"Argue AGAINST: {topic}"))
    judge_text = str(judge(f"Topic: {topic}\nFOR: {advocate_text}\nAGAINST: {skeptic_text}"))

    print(f"Advocate: {advocate_text[:150]}...")
    print(f"Skeptic: {skeptic_text[:150]}...")
    print(f"Judge: {judge_text}")

    # Prepare data for Graphiti
    debate_record = {
        "type": "debate_outcome",
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "advocate_points": advocate_text,
        "skeptic_points": skeptic_text,
        "recommendation": judge_text,
        "pattern": "advocate_skeptic_judge"
    }

    print("\n[Saving to Graph Memory]")
    print(f"Record to persist: {json.dumps(debate_record, indent=2)[:300]}...")

    # Note: Graphiti integration would use MCP tools
    # This demonstrates the data structure for persistence
    print("\nTo persist, use Graphiti MCP add_memory tool with:")
    print(f"  group_id: 'aws_agent_1-debates'")
    print(f"  name: 'Debate: {topic[:30]}...'")
    print(f"  source: 'json'")

    return {
        "topic": topic,
        "advocate": advocate_text,
        "skeptic": skeptic_text,
        "judge": judge_text,
        "record": debate_record
    }


# =============================================================================
# Iteration 5: Full Graphiti Round-Trip
# =============================================================================
def graphiti_roundtrip_demo():
    """
    Full round-trip: persist debate → retrieve for new related debate.

    This demonstrates cross-session learning:
    1. Search Graphiti for past debates on related topics
    2. Use past insights to inform the Judge's synthesis
    3. Persist new debate outcome for future reference

    Note: Requires Graphiti MCP server and pre-populated debate data.
    Run via Claude Code to use actual MCP tools.
    """
    print("\n" + "=" * 60)
    print("Iteration 5: Full Graphiti Round-Trip")
    print("=" * 60)

    # New but RELATED topic (builds on TypeScript/microservices debates)
    topic = "Should we use a monorepo structure for our TypeScript microservices?"

    print(f"\nTopic: {topic}")
    print("\n[Step 1: Search for related past debates]")

    # Simulate what we'd retrieve from Graphiti
    # In production, this would come from mcp__graphiti-memory__search_memory_facts
    past_debates = """
PAST DEBATE 1: TypeScript vs JavaScript
- Recommendation: Adopt TypeScript for larger projects with training
- Key insight: Static typing helps manage large codebases
- Confidence: 7/10

PAST DEBATE 2: Microservices vs Monolith
- Recommendation: Phased approach, start with high-scaling modules
- Key insight: Distributed systems add complexity; data management is challenging
- Confidence: 6/10
"""
    print(f"Retrieved past debates:\n{past_debates}")

    # Create agents with context-aware Judge
    advocate = Agent(
        model=fast_model,
        system_prompt="Argue FOR monorepo structure for TypeScript microservices. Be concise: 3 key points.",
        callback_handler=None
    )

    skeptic = Agent(
        model=fast_model,
        system_prompt="Argue AGAINST monorepo. Be concise: 3 key concerns.",
        callback_handler=None
    )

    # Judge has access to past debate context
    judge = Agent(
        model=fast_model,
        system_prompt=f"""Synthesize debate with awareness of past organizational decisions.

PAST DEBATES (for context):
{past_debates}

Consider how this decision relates to past choices.
Give: RECOMMENDATION (1 sentence), CONFIDENCE (1-10), RELATES_TO (which past debates).""",
        callback_handler=None
    )

    print("\n[Step 2: Run new debate with past context]")

    advocate_text = str(advocate(f"Argue FOR: {topic}"))
    print(f"Advocate: {advocate_text[:200]}...")

    skeptic_text = str(skeptic(f"Argue AGAINST: {topic}"))
    print(f"Skeptic: {skeptic_text[:200]}...")

    judge_text = str(judge(f"Topic: {topic}\nFOR: {advocate_text}\nAGAINST: {skeptic_text}"))
    print(f"\nJudge (with past context):\n{judge_text}")

    print("\n[Step 3: Prepare new debate for persistence]")

    new_debate = {
        "type": "debate_outcome",
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "advocate_points": advocate_text,
        "skeptic_points": skeptic_text,
        "recommendation": judge_text,
        "pattern": "advocate_skeptic_judge",
        "related_debates": ["TypeScript vs JavaScript", "Microservices vs Monolith"]
    }

    print(f"New debate to persist:")
    print(f"  Topic: {new_debate['topic']}")
    print(f"  Related to: {new_debate['related_debates']}")
    print(f"  Recommendation: {judge_text[:100]}...")

    print("\n[Round-trip complete]")
    print("Pattern: Search past → Inform judge → Persist new → Build knowledge graph")

    return {
        "topic": topic,
        "past_context": past_debates,
        "advocate": advocate_text,
        "skeptic": skeptic_text,
        "judge": judge_text,
        "new_debate": new_debate
    }


# =============================================================================
# Main Demo
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Level 18: Debate Pattern Demos")
    print("=" * 60)

    # Run all iterations
    print("\n[Iteration 1: Basic Debate]")
    result1 = basic_debate_demo()

    print("\n[Iteration 2: Multi-Round Debate]")
    result2 = multi_round_debate_demo(num_rounds=2)

    print("\n[Iteration 3: Code Review Debate]")
    result3 = code_review_debate_demo()

    print("\n[Iteration 4: Graph Memory Integration]")
    result4 = graph_memory_debate_demo()

    print("\n[Iteration 5: Full Graphiti Round-Trip]")
    result5 = graphiti_roundtrip_demo()

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"""
Iteration 1 (Basic Debate): Sequential Advocate → Skeptic → Judge
  - Good for: Quick decisions, simple tradeoffs
  - Trade-off: Single pass may miss nuances

Iteration 2 (Multi-Round): {result2['rounds']} rounds with scoring
  - Scores: Advocate {result2['scores']['advocate']} - Skeptic {result2['scores']['skeptic']}
  - Good for: Complex decisions, thorough analysis
  - Trade-off: Higher cost, longer execution

Iteration 3 (Code Review): Adversarial code review
  - Good for: Balanced reviews, catching blind spots
  - Trade-off: May over-complicate simple reviews

Iteration 4 (Graph Memory): Persist for learning
  - Good for: Cross-session patterns, decision history
  - Trade-off: Storage overhead, retrieval latency

Iteration 5 (Round-Trip): Search past → Inform judge → Persist new
  - Good for: Building organizational knowledge, informed decisions
  - Trade-off: Requires Graphiti infrastructure, retrieval latency
  - Key pattern: Judge prompt includes past debate context
""")
