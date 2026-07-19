---
name: code-review
description: Security, performance, and correctness review of code changes
allowed_tools:
  - read_file
---

# Code Review Skill

You are now equipped to perform thorough code reviews. Apply this checklist systematically:

## Step 1: Correctness
- Does the code do what the description/comments claim?
- Are edge cases handled: empty input, null values, off-by-one, integer overflow?
- Are all error paths returning or raising appropriately?

## Step 2: Security (OWASP Top 10)
- SQL injection: are all queries parameterised?
- XSS: is user input escaped before rendering?
- Auth: are sensitive endpoints protected? Are tokens validated?
- Secrets: are credentials hardcoded anywhere?
- Dependency: are imported libraries pinned and non-vulnerable?

## Step 3: Performance
- Are there N+1 query patterns (loop calling DB inside loop)?
- Are large collections iterated multiple times when once would do?
- Are expensive operations cached where safe?
- Is there unnecessary blocking I/O in async contexts?

## Step 4: Maintainability
- Are functions under 30 lines and single-purpose?
- Are magic numbers replaced with named constants?
- Is error handling specific (not bare `except Exception`)?
- Are variable names descriptive?

## Output Format
Rate each area: PASS / WARN / FAIL

- **Correctness**: [rating] — [findings]
- **Security**: [rating] — [findings]
- **Performance**: [rating] — [findings]
- **Maintainability**: [rating] — [findings]
- **Overall verdict**: APPROVE / REQUEST CHANGES
- **Required changes**: numbered list (if any)
