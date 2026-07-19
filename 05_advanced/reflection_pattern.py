"""
Level 11: Reflection Pattern
=============================
Agent self-critique and iterative improvement patterns.

Three Patterns:
1. Inner Critic: Same agent reviews its own output
2. External Critic: Separate critic agent evaluates
3. Iterative Refinement: Loop until quality threshold

Key Concepts:
- Self-critique improves output quality
- Quality scoring enables automated refinement
- Cost/latency tradeoffs with iteration count

Run: uv run python 05_advanced/reflection_pattern.py
"""

import json
import re
import sys
sys.path.insert(0, ".")

from strands import Agent
from tools import get_model

# Models: gemini-flash for generation (fast), gpt-5-nano for critique (OpenAI)
generator_model = get_model("gemini-flash")
critic_model = get_model("gpt-5-nano")


# =============================================================================
# Pattern 1: Inner Critic
# =============================================================================
def inner_critic_demo():
    """Same agent generates content, then critiques and improves it."""
    print("\n" + "=" * 60)
    print("Pattern 1: Inner Critic")
    print("=" * 60)

    agent = Agent(
        model=critic_model,  # Use stronger model for self-reflection
        system_prompt="""You are a creative writer who can also critique your own work.
When asked to write something, produce quality content.
When asked to critique and improve, be honest about weaknesses and make concrete improvements.""",
        callback_handler=None  # Clean programmatic access
    )

    # Phase 1: Generate
    print("\n[Phase 1: Generate]")
    initial = agent("Write a haiku about AI agents learning.")
    initial_text = str(initial)
    print(f"Initial haiku:\n{initial_text}")

    # Phase 2: Self-critique and improve
    print("\n[Phase 2: Self-Critique]")
    improved = agent(f"""Review your haiku and improve it. Be specific about what's wrong.

Your haiku was:
{initial_text}

Requirements for a good haiku:
- 5-7-5 syllable structure
- Evocative imagery
- Captures a moment or emotion

Provide your critique, then write an improved version.""")
    print(f"Self-critique and improvement:\n{str(improved)}")

    return {"initial": initial_text, "improved": str(improved)}


# =============================================================================
# Pattern 2: External Critic
# =============================================================================
def external_critic_demo():
    """Generator agent + separate Critic agent."""
    print("\n" + "=" * 60)
    print("Pattern 2: External Critic")
    print("=" * 60)

    # Generator: Fast model, focused on creation
    generator = Agent(
        model=generator_model,
        system_prompt="""You are a creative haiku writer.
Write evocative haikus that follow 5-7-5 syllable structure.
Focus on imagery and capturing a single moment.""",
        callback_handler=None
    )

    # Critic: Stronger model, focused on evaluation
    critic = Agent(
        model=critic_model,
        system_prompt="""You are a poetry critic specializing in haiku.
Evaluate haikus based on:
1. Syllable structure (5-7-5)
2. Imagery quality
3. Emotional resonance
4. Traditional haiku elements (kigo, kireji)

Provide specific, actionable feedback.""",
        callback_handler=None
    )

    # Generate
    print("\n[Generator creates haiku]")
    haiku = generator("Write a haiku about morning coffee.")
    haiku_text = str(haiku)
    print(f"Generated haiku:\n{haiku_text}")

    # Critique
    print("\n[Critic evaluates]")
    critique = critic(f"""Evaluate this haiku and provide specific feedback:

{haiku_text}

Format your response as:
STRENGTHS: (what works well)
WEAKNESSES: (what needs improvement)
SCORE: (1-10)
SUGGESTIONS: (specific improvements)""")
    print(f"Critique:\n{str(critique)}")

    return {"haiku": haiku_text, "critique": str(critique)}


# =============================================================================
# Pattern 3: Iterative Refinement
# =============================================================================
def parse_score(text: str) -> int:
    """Extract numeric score from critic response."""
    # Look for "SCORE: N" or "N/10" patterns
    patterns = [
        r'SCORE:\s*(\d+)',
        r'(\d+)\s*/\s*10',
        r'score[:\s]+(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            score = int(match.group(1))
            return min(10, max(1, score))  # Clamp to 1-10
    return 5  # Default if no score found


def iterative_refinement_demo(max_iterations: int = 4, threshold: int = 8):
    """Loop until quality threshold met or max iterations reached."""
    print("\n" + "=" * 60)
    print("Pattern 3: Iterative Refinement")
    print(f"(threshold: {threshold}/10, max iterations: {max_iterations})")
    print("=" * 60)

    # Generator: Creates and improves content
    generator = Agent(
        model=generator_model,
        system_prompt="""You are a haiku writer who can create and improve haikus.
Follow 5-7-5 syllable structure strictly.
Focus on vivid imagery and emotional resonance.""",
        callback_handler=None
    )

    # Critic: Scores and provides feedback
    critic = Agent(
        model=critic_model,
        system_prompt="""You are a strict haiku judge.
Score haikus from 1-10 based on:
- Syllable count accuracy (5-7-5)
- Imagery vividness
- Emotional impact
- Overall craft

Be honest and strict. Only give 8+ to excellent haikus.
Always include "SCORE: N" in your response.""",
        callback_handler=None
    )

    # Track iterations
    history = []
    current_haiku = None
    current_score = 0

    for iteration in range(1, max_iterations + 1):
        print(f"\n[Iteration {iteration}]")

        # Generate or improve
        if current_haiku is None:
            prompt = "Write a haiku about autumn leaves falling."
            response = generator(prompt)
        else:
            prompt = f"""Improve this haiku based on the feedback:

Current haiku:
{current_haiku}

Feedback: {history[-1]['feedback']}

Write an improved version that addresses the feedback."""
            response = generator(prompt)

        current_haiku = str(response)
        print(f"Haiku:\n{current_haiku}")

        # Get score and feedback
        critique_response = critic(f"""Score this haiku strictly (1-10):

{current_haiku}

Provide:
SCORE: [1-10]
FEEDBACK: [specific improvements needed]""")

        critique_text = str(critique_response)
        current_score = parse_score(critique_text)
        print(f"Score: {current_score}/10")

        # Record history
        history.append({
            "iteration": iteration,
            "haiku": current_haiku,
            "score": current_score,
            "feedback": critique_text
        })

        # Check convergence
        if current_score >= threshold:
            print(f"\nConverged at iteration {iteration} with score {current_score}/10")
            break
    else:
        print(f"\nMax iterations ({max_iterations}) reached. Final score: {current_score}/10")

    # Summary
    print("\n[Iteration History]")
    for entry in history:
        print(f"  Iteration {entry['iteration']}: Score {entry['score']}/10")

    return {
        "final_haiku": current_haiku,
        "final_score": current_score,
        "iterations": len(history),
        "history": history
    }


# =============================================================================
# Main Demo
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Level 11: Reflection Pattern Demos")
    print("=" * 60)

    # Run all three patterns
    print("\nRunning Pattern 1: Inner Critic...")
    result1 = inner_critic_demo()

    print("\nRunning Pattern 2: External Critic...")
    result2 = external_critic_demo()

    print("\nRunning Pattern 3: Iterative Refinement...")
    result3 = iterative_refinement_demo()

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"""
Pattern 1 (Inner Critic): Same agent self-reflects
  - Good for: Simple tasks, low cost
  - Trade-off: May not catch own blind spots

Pattern 2 (External Critic): Separate evaluator
  - Good for: Objective feedback, specialized evaluation
  - Trade-off: Higher cost (two agents)

Pattern 3 (Iterative Refinement): Loop until quality met
  - Iterations: {result3['iterations']}
  - Final score: {result3['final_score']}/10
  - Good for: High-quality output requirements
  - Trade-off: Variable cost, latency depends on convergence
""")
