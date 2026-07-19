"""Level 98: The sandbox tier — Strands Shell (in-process) vs a container (Podman).

Three ways to give an agent a command line, at very different cost/isolation:
  1. Strands Shell   — in-process virtual shell (VFS + mediation), NO fork/exec/container.
  2. Container        — real OS isolation via `podman exec` (a ~30-line PodmanSandbox: the SDK
                        ships DockerSandbox, whose only docker-specific line is the binary name;
                        Podman's CLI is docker-compatible, and here the docker daemon is down while
                        podman is up, so Podman is the working runtime).
  3. AgentCore Code Interpreter — managed cloud sandbox (L72, `16_agentcore_tools/code_interpreter.py`),
                        referenced as the cloud tier; not re-run here (spends AWS; already characterized).

Claims are limited to what the readable source (`strands_shell/__init__.py`) guarantees and what is
observable in this harness:
  - latency (cold start, per-command) — measured;
  - VFS isolation — a no-bind Shell has NO host filesystem access (source: in-process VFS; observed:
    a no-bind shell cannot read /etc/passwd);
  - secret non-exposure — a `Cred(token=...)` is held in the native layer and `ConfigCred` NEVER
    reports the token (source lines 129-132, 383-385); observed absent from both `config` and `env`.
The network URL-allowlist ENFORCEMENT lives in the native Rust extension and is NOT asserted here
(it could not be exercised in this harness — the builtin curl produced no observable egress); the
allowlist is only shown as CONFIGURED via `Shell.config.allowed_urls`.

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

    # --- isolation: the in-process VFS has NO host filesystem access (source: in-process VFS) ---
    nobind = ss.Shell()
    passwd = nobind.run("cat /etc/passwd")          # host file: must not be readable
    host_probe = nobind.run(f"cat {__file__}")       # this very source file on the host
    print(f"  [VFS isolation] no-bind shell: cat /etc/passwd status={passwd.status} (nonzero=isolated); "
          f"cat <host file> status={host_probe.status}")

    # --- secret non-exposure: Cred(token=...) is held natively; ConfigCred NEVER carries the token ---
    secret = "sk-l98-" + "SEEKRIT"
    cred_shell = ss.Shell(allowed_urls=["https://example.com/*"],
                          credentials=[ss.Cred(url="https://example.com/*", token=secret)])
    in_env = secret in cred_shell.run("env").stdout
    in_config = secret in str(cred_shell.config)     # config is a @property (read from source)
    allowlisted = list(cred_shell.config.allowed_urls)
    print(f"  [secret non-exposure] token in `env`={in_env}  in `config`={in_config}  "
          f"(allowlist CONFIGURED={allowlisted}; native enforcement not asserted here)\n")

    battery_match = shell_out == pod_out
    checks = {
        "Strands Shell cold start is sub-millisecond-class (<10 ms)": shell_cold < 10,
        "Shell per-command is far faster than a container exec (p50)": shell_p50 < pod_p50,
        "both backends produce identical output on the command battery": battery_match,
        "VFS isolates the host FS: no-bind shell cannot read /etc/passwd": passwd.status != 0,
        "VFS isolates the host FS: no-bind shell cannot read a host source file": host_probe.status != 0,
        "injected secret is absent from the config snapshot (source-guaranteed)": not in_config,
        "injected secret is absent from the shell environment": not in_env,
        "allowlist is recorded in the config snapshot": allowlisted == ["https://example.com/*"],
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    _podman("rm", "-f", CONTAINER)  # teardown
    _LOOP.close()
    assert all(checks.values()), "L98 FAILED — a sandbox-tier check did not hold"
    print("\n[L98] PASS — Strands Shell is an in-process sandbox (sub-ms cold start, "
          f"~{pod_p50/max(shell_p50,0.001):.0f}x faster per command than a Podman exec) with a real VFS "
          "boundary (no host FS access) and secrets held out of config/env; the container tier buys "
          "OS-level isolation at container-startup cost. PodmanSandbox shows the Sandbox protocol is a "
          "swappable seam. Network-allowlist enforcement is native and not asserted here.")


if __name__ == "__main__":
    main()
