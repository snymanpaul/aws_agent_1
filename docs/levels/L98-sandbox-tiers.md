# L98: The Sandbox Tier — Strands Shell vs a Container (Podman)

**Code:** `16_agentcore_tools/sandbox_tiers.py`
**Reflection:** [`level-98-reflection.md`](../../.claude/learnings/reflections/level-98-reflection.md)

**Status:** Done (Tier 22, 2026-07-19, local — needs podman + alpine, no AWS).

Three ways to give an agent a command line, measured rather than asserted from marketing:

| Tier | Cold start | Per command | Isolation |
|------|-----------|-------------|-----------|
| Strands Shell (in-process VFS) | **5 ms** | **0.022 ms** (p50) | in-process VFS; no host FS access; secret held natively |
| Podman container (`PodmanSandbox`) | 179 ms provision | 125 ms (p50) | OS-level (namespace) |
| AgentCore Code Interpreter (L72) | — | network round-trip | managed cloud |

Strands Shell is **~5600× faster per command** than a Podman exec — the in-process VFS trades
OS-level isolation for speed.

**PodmanSandbox — the swappable seam:** `strands.sandbox.DockerSandbox`'s only docker-specific line
is the binary name it passes to the process spawner; a ~15-line subclass overriding
`execute_streaming` to pass `"podman"` runs verbatim (Podman's CLI is docker-compatible). On this
machine the Docker daemon was down and Podman up, so Podman was also the only working runtime.

**Source-grounded security claims** (from reading `strands_shell/__init__.py` in full, then
observing):
- **VFS isolation** — a no-bind `Shell` cannot read `/etc/passwd` or a host source file (status 1).
- **Secret non-exposure** — a `Cred(token=…)` is held in the native layer; `ConfigCred` never
  carries the token (source lines 129–132, 383–385), and the raw secret is absent from both
  `config` and `env`.
- **Network allowlist** — reported as **configured** (`Shell.config.allowed_urls`) but **not
  asserted as enforced**: enforcement lives in the native Rust extension and could not be exercised
  in this harness (the builtin curl showed no observable egress difference).

**Process note (the real lesson):** the first drafts asserted a "working SSRF guard" and mis-modeled
`Output`/`Cred`/`config` from training-knowledge priors; each was refuted by trial. The fix was to
read the one authoritative source module fully and assert only what it documents and the harness can
observe — grounding every claim in bytes, and scoping down claims behind an unreadable boundary.
