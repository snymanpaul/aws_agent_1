# L98: The Sandbox Tier — Strands Shell vs a Container (Podman)

**Code:** `16_agentcore_tools/sandbox_tiers.py`
**Reflection:** [`level-98-reflection.md`](../../.claude/learnings/reflections/level-98-reflection.md)

**Status:** Done (Tier 22, 2026-07-19, local — needs podman + alpine, no AWS). Security claims
grounded in the cloned Rust source (`github.com/strands-agents/shell`) and empirically verified.

Three ways to give an agent a command line, measured:

| Tier | Cold start | Per command | Isolation |
|------|-----------|-------------|-----------|
| Strands Shell (in-process VFS) | **5 ms** | **0.022 ms** (p50) | in-process VFS + SSRF guard |
| Podman container (`PodmanSandbox`) | ~278 ms provision | ~140 ms (p50) | OS-level (namespace) |
| AgentCore Code Interpreter (L72) | — | network round-trip | managed cloud |

Strands Shell is **~5700× faster per command** than a Podman exec.

**PodmanSandbox — the swappable seam:** `DockerSandbox`'s only docker-specific line is the binary
name it passes to the process spawner; a ~15-line subclass overriding `execute_streaming` to pass
`"podman"` runs verbatim. On this machine the Docker daemon was down and Podman up, so Podman was
also the only working runtime.

## Security model (read from `src/vfs_kernel.rs` + `src/commands/curl.rs`, then verified live)

- **VFS isolation** — a no-bind `Shell` cannot read `/etc/passwd` or a host source file (status 1).
- **SSRF guard (the headline)** — `check_url_safe` + `is_ip_blocked` + a DNS `SafeResolver` block
  loopback, private, link-local, IMDS (169.254.169.254 **and** the IPv4-mapped `[::ffff:…]` bypass),
  and `localhost`, while permitting public hosts. Verified: all six blocked with curl exit 1
  `access denied: <host>`; `example.com` returns real HTML (exit 0). Allowlist matching is on the
  **parsed** scheme+host+port (not a string prefix), which closes userinfo-injection SSRF escapes.
- **Allowlist = ADDITIVE TRUST, not deny-by-default** — `check_url` allows a URL matching an
  allowlist prefix, else falls to `check_url_safe`. A public URL is reachable with or without the
  allowlist; the allowlist's job is to **permit an otherwise-SSRF-blocked internal URL**. Verified:
  `allowed_urls=["http://127.0.0.1:9/"]` makes a loopback URL reach the connection stage (curl exit
  6 conn-error, not exit 1 access-denied).
  - **Gotcha (verified):** `url_matches_prefix` does segment-boundary **path** matching, so a
    host-wide entry must end in `/`. The `/*` form (seen in some docstrings) is a **literal path**
    that fails to match `/` and silently leaves the URL SSRF-blocked — fail-closed but surprising.
- **Secret non-exposure** — `Cred(url, token)` is injected as an `Authorization: Bearer <token>`
  header on the outbound request (`resolve_credential`, with prefix-confusion + method guards); the
  token is held natively and is absent from both `config` and `env`.

## Process note (why this was redone)

The first pass guessed the shell's behavior from training priors and, when the allowlist didn't
block a public host, wrongly concluded the network enforcement was "unobservable" and dropped the
claim. Cloning the Rust source showed the allowlist is additive trust and the real guard is the
default SSRF block — fully observable. The corrected lesson asserts six precise SSRF facts plus the
`/*` gotcha. The standing rule captured: **git clone the source repo and ground every claim in the
actual source, not in how a "shell" or "curl" is assumed to behave.**
