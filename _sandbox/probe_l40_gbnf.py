"""
Probe: Does Ollama pass GBNF grammar params through to llama.cpp or silently ignore them?

Method:
- Send a request with extra_body={"grammar": "..."} to Ollama
- If grammar is respected: response tokens are constrained to the grammar
- If silently ignored: response is unconstrained natural language

GBNF grammar used: force the model to only output "YES" or "NO"
A free-response question whose natural answer is longer text.
"""
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

# Simple GBNF grammar that only allows "YES" or "NO" followed by newline
# From llama.cpp GBNF spec: root := ("YES" | "NO") "\n"
grammar = r'''root ::= ("YES" | "NO") "\n"'''

print(f"Grammar: {grammar!r}\n")
print("Question: What is the capital of France? (natural answer would be 'Paris')")
print("If grammar is respected: output should be only 'YES' or 'NO'")
print("If grammar is ignored: output should contain 'Paris' or a sentence\n")

response = client.chat.completions.create(
    model="llama3.2:3b",
    messages=[
        {"role": "user", "content": "What is the capital of France? Answer YES or NO."},
    ],
    extra_body={"grammar": grammar},
    max_tokens=20,
)

content = response.choices[0].message.content
print(f"Response: {content!r}")
print()

# Check if the grammar was respected
stripped = (content or "").strip()
if stripped in ("YES", "NO"):
    print("RESULT: Grammar RESPECTED — output was constrained to YES/NO")
else:
    print("RESULT: Grammar appears IGNORED — output was not constrained to YES/NO")
    print("Note: This may also indicate the grammar was processed but the model answered the question naturally.")
    print("      To confirm: try with a grammar that restricts to digits only and check a free-text response.")
