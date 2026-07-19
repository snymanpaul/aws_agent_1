"""Level 98: The sandbox tier — Strands Shell (in-process) vs a container (Podman).

Three ways to give an agent a command line, at very different cost/isolation:
  1. Strands Shell   — in-process virtual shell (VFS + mediation), NO fork/exec/container.
  2. Container        — real OS isolation via `podman exec` (a ~30-line PodmanSandbox: the SDK
                        ships DockerSandbox, whose only docker-specific line is the binary name;
                        Podman's CLI is docker-compatible, and here the docker daemon is down while
                        podman is up, so Podman is the working runtime).
  3. AgentCore Code Interpreter — managed cloud sandbox (L72, `16_agentcore_tools/code_interpreter.py`),
                        referenced as the cloud tier; not re-run here (spends AWS; already characterized).

Every claim below is grounded in the ACTUAL Rust source (cloned github.com/strands-agents/shell,
`src/commands/curl.rs` + `src/vfs_kernel.rs`) AND empirically verified against the installed native
extension:
  - latency (cold start, per-command) — measured;
  - VFS isolation — a no-bind Shell has NO host filesystem access (in-process VFS);
  - SSRF guard — the headline security property. `vfs_kernel::check_url_safe` + `is_ip_blocked` +
    a DNS `SafeResolver` block loopback / private / link-local / IMDS (169.254.169.254, incl. the
    IPv4-mapped `[::ffff:169.254.169.254]` bypass) / localhost, while permitting public hosts.
    Observed: those return curl exit 1 "access denied: <host>"; https://example.com returns real
    HTML (exit 0).
  - allowlist = ADDITIVE TRUST, not deny-by-default. `check_url` allows a URL matching an allowlist
    prefix, ELSE falls to `check_url_safe`. A public URL is reachable with or without the allowlist;
    the allowlist PERMITS an otherwise-SSRF-blocked internal URL. GOTCHA (verified):
    `url_matches_prefix` does segment-boundary PATH matching, so a host-wide entry must end in `/`;
    the `/*` form is a LITERAL path that fails to match `/` and silently leaves the URL blocked.
  - secret non-exposure — a `Cred(token=...)` is injected as `Authorization: Bearer <token>` on the
    outbound request (vfs_kernel::resolve_credential), held natively; `ConfigCred` never reports the
    token; observed absent from both `config` and `env`.

Prior draft error (corrected): an earlier version guessed the allowlist was deny-by-default and,
when a public URL was not blocked, wrongly concluded enforcement was "unobservable". The Rust source
shows the allowlist is additive trust and the real guard is the default SSRF block — which IS
observable and is now asserted.

Run: LESSON_DOTENV=<dotenv> uv run python 16_agentcore_tools/sandbox_tiers.py   (needs podman + alpine)
"""

import asyncio
import statistics
import subprocess
import time
from typing import Any, AsyncGenerator

import strands_shell as ss
from strands.sandbox.docker import DockerSandbox
from strands.sandbox.stream_process import _stream_process
from strands.sandbox.types import ExecutionResult

IMAGE = "alpine:latest"
CONTAINER = "l98-podman-sbx"


# --------------------------------------------------------------- the swappable seam: PodmanSandbox
class PodmanSandbox(DockerSandbox):
    """DockerSandbox with the container runtime swapped to podman. Only execute_streaming differs —
    it passes 'podman' (not 'docker') to the process spawner; the `podman exec` argv is identical."""

    async def execute_streaming(self, command: str, *, timeout=None, cwd=None, env=None, **kwargs
                                ) -> AsyncGenerator[Any, None]:
        args = ["exec"]
        if self._user is not None:
            args += ["--user", self._user]
        effective_cwd = cwd if cwd is not None else self.working_dir
        if effective_cwd is not None:
            args += ["-w", effective_cwd]
        if env:
            for key, value in env.items():
                args += ["-e", f"{key}={value}"]
        args += ["--", self.container, "sh", "-c", command]
        async for chunk in _stream_process("podman", args, timeout=timeout,
                                           enoent_message="podman is not installed or not on PATH"):
            yield chunk


def _podman(*a):
    return subprocess.run(["podman", *a], capture_output=True, text=True, timeout=60)


# One persistent event loop for all podman execs (asyncio.run per-call churns loops + warns).
_LOOP = asyncio.new_event_loop()


# Shared battery — only constructs both the minimal Strands shell and alpine busybox support
# (no GNU-only flags like `head -c` / `head -1`, which the Strands builtins reject).
BATTERY = [
    "echo hello > /tmp/f.txt && cat /tmp/f.txt",           # file ops -> hello
    "printf 'a,1\\nb,2\\nc,3\\n' | grep b | cut -d, -f2",   # grep + cut -> 2
    "echo one two three | tr ' ' '-'",                      # tr -> one-two-three
]


def run_shell_battery(sh) -> list[str]:
    return [sh.run(c).stdout.strip() for c in BATTERY]


async def _podman_exec_async(sb, cmd) -> str:
    result = None
    async for chunk in sb.execute_streaming(cmd):
        if isinstance(chunk, ExecutionResult):
            result = chunk
    return (result.stdout if result else "").strip()


def pexec(sb, cmd) -> str:
    return _LOOP.run_until_complete(_podman_exec_async(sb, cmd))


def run_podman_battery(sb) -> list[str]:
    return [pexec(sb, c) for c in BATTERY]


# --------------------------------------------------------------- timing
def time_ms(fn, iters=20) -> tuple[float, float]:
    xs = []
    for _ in range(iters):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000)
    xs.sort()
    return statistics.median(xs), xs[int(len(xs) * 0.95)]


def main() -> None:
    print("[L98] sandbox tier — Strands Shell (in-process) vs Podman container\n")

    # --- Strands Shell: cold start + per-command latency ---
    t = time.perf_counter(); ss.Shell(); shell_cold = (time.perf_counter() - t) * 1000
    sh = ss.Shell()
    shell_p50, shell_p95 = time_ms(lambda: sh.run("echo x"))
    shell_out = run_shell_battery(sh)
    print(f"  Strands Shell : cold_start={shell_cold:.2f} ms  per_cmd p50={shell_p50:.3f} p95={shell_p95:.3f} ms")

    # --- Podman container: ensure running, then cold-exec + per-command ---
    _podman("rm", "-f", CONTAINER)
    t = time.perf_counter()
    _podman("run", "-d", "--name", CONTAINER, IMAGE, "sleep", "3600")
    pod_provision = (time.perf_counter() - t) * 1000
    sb = PodmanSandbox(CONTAINER)
    t = time.perf_counter(); pexec(sb, "echo x"); pod_cold = (time.perf_counter() - t) * 1000
    pod_p50, pod_p95 = time_ms(lambda: pexec(sb, "echo x"))
    pod_out = run_podman_battery(sb)
    print(f"  Podman        : provision={pod_provision:.0f} ms  first_exec={pod_cold:.1f} ms  "
          f"per_cmd p50={pod_p50:.1f} p95={pod_p95:.1f} ms")
    print(f"  (L72 AgentCore Code Interpreter is the managed cloud tier — network round-trip per call)\n")

    # --- isolation: the in-process VFS has NO host filesystem access ---
    nobind = ss.Shell()
    passwd = nobind.run("cat /etc/passwd")
    host_probe = nobind.run(f"cat {__file__}")
    print(f"  [VFS isolation] no-bind shell: cat /etc/passwd status={passwd.status} (nonzero=isolated); "
          f"cat <host file> status={host_probe.status}")

    # --- SSRF guard: default shell blocks loopback/private/link-local/IMDS/localhost, allows public ---
    def curl(shell, url):
        return shell.run(f"curl -s -S -w 'CODE=%{{http_code}}' {url}")

    ssrf_targets = {
        "IMDS 169.254.169.254": "http://169.254.169.254/latest/meta-data/",
        "IPv4-mapped IMDS": "http://[::ffff:169.254.169.254]/",
        "loopback 127.0.0.1": "http://127.0.0.1/",
        "localhost": "http://localhost/",
        "IPv6 loopback ::1": "http://[::1]/",
        "private 10.0.0.1": "http://10.0.0.1/",
    }
    blocked = {name: curl(nobind, url) for name, url in ssrf_targets.items()}
    for name, o in blocked.items():
        print(f"  [SSRF] {name:22s} -> status={o.status} err={o.stderr.strip()[:44]!r}")
    public = curl(nobind, "https://example.com/")
    print(f"  [SSRF] public example.com     -> status={public.status} (reachable; not access-denied)")

    # --- allowlist = additive trust; segment-boundary path match (host-wide entry needs trailing '/') ---
    trailing = curl(ss.Shell(allowed_urls=["http://127.0.0.1:9/"]), "http://127.0.0.1:9/")   # bypasses SSRF -> conn error 6
    star = curl(ss.Shell(allowed_urls=["http://127.0.0.1:9/*"]), "http://127.0.0.1:9/")       # '/*' literal -> still blocked (1)
    print(f"  [allowlist] entry 'http://127.0.0.1:9/'  -> status={trailing.status} "
          f"(6=conn error: SSRF bypassed); '/*' form -> status={star.status} (1=still blocked: '/*' gotcha)")

    # --- secret non-exposure: Cred(token=...) -> Authorization: Bearer header, never in env/config ---
    secret = "sk-l98-" + "SEEKRIT"
    cred_shell = ss.Shell(credentials=[ss.Cred(url="https://example.com/", token=secret)])
    in_env = secret in cred_shell.run("env").stdout
    in_config = secret in str(cred_shell.config)     # config is a @property (verified in source)
    print(f"  [secret non-exposure] token in `env`={in_env}  in `config`={in_config} "
          f"(injected as Authorization: Bearer, held natively)\n")

    battery_match = shell_out == pod_out
    ssrf_all_blocked = all(o.status == 1 and "access denied" in o.stderr for o in blocked.values())
    checks = {
        "Strands Shell cold start is sub-millisecond-class (<10 ms)": shell_cold < 10,
        "Shell per-command is far faster than a container exec (p50)": shell_p50 < pod_p50,
        "both backends produce identical output on the command battery": battery_match,
        "VFS isolates the host FS: no-bind shell cannot read /etc/passwd": passwd.status != 0,
        "SSRF guard blocks ALL of loopback/private/link-local/IMDS/localhost (access denied)": ssrf_all_blocked,
        "SSRF positive control: a public host is reachable (not access-denied)": public.status == 0,
        "allowlist ADDS trust: 'http://host/' bypasses SSRF (conn error, not access-denied)": trailing.status == 6,
        "gotcha: the '/*' allowlist form does NOT match '/' -> stays SSRF-blocked": star.status == 1,
        "injected secret is absent from the config snapshot (source-guaranteed)": not in_config,
        "injected secret is absent from the shell environment": not in_env,
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    _podman("rm", "-f", CONTAINER)  # teardown
    _LOOP.close()
    assert all(checks.values()), "L98 FAILED — a sandbox-tier check did not hold"
    print("\n[L98] PASS — Strands Shell is an in-process sandbox (sub-ms cold start, "
          f"~{pod_p50/max(shell_p50,0.001):.0f}x faster per command than a Podman exec) with a real VFS "
          "boundary (no host FS access), a working SSRF guard (loopback/private/IMDS/localhost blocked, "
          "public allowed), and secrets injected as Bearer headers never exposed in env/config. The "
          "allowlist is additive trust (permits internal URLs), with a segment-boundary path-match "
          "gotcha ('/*' != '/'). The container tier buys OS-level isolation at container-startup cost; "
          "PodmanSandbox shows the Sandbox protocol is a swappable seam.")


if __name__ == "__main__":
    main()
