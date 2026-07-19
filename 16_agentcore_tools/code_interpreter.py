"""
Level 72: AgentCore Code Interpreter — A Managed Sandbox an Agent Can Run Code In
================================================================================
AWS Bedrock AgentCore — `bedrock_agentcore.tools.code_interpreter_client`.

Goal: give an agent a SECURE place to execute arbitrary code. AgentCore's Code
Interpreter is a managed, isolated sandbox (a persistent kernel + filesystem) you
reach over one `code_session(...)` context manager — start it, run code/shell,
move files, then it tears down. This is the production-grade version of L24's
local subprocess/Docker tool-synthesis sandbox.

Why a managed sandbox:
    Letting an LLM run code it wrote is powerful and dangerous. Doing it in a
    local subprocess risks your machine; doing it in AgentCore's sandbox isolates
    it (AWS-side), gives it a real Python kernel with state + a filesystem, and
    optionally network for `pip`. You get capability without giving the model your
    laptop.

Depends on: L24 (tool synthesis — the local/unsafe version), L27 (AgentCore plane)
Unlocks:    L73 (AgentCore Browser — the sibling managed tool), safe agentic code-run

Iterations:
  1. Execute code -> structured result   — stdout / stderr / exitCode, not just text.
  2. The session is STATEFUL             — a variable from call 1 is alive in call 2;
                                           clear_context resets the kernel.
  3. Shell + a persistent filesystem     — execute_command writes a file; code reads
                                           it back; best-effort package install.
  4. Wire it to a Strands agent          — an agent solves a task by WRITING and
                                           RUNNING Python in the sandbox.

Critical API facts (validated by live probe, not docs):
    * from bedrock_agentcore.tools.code_interpreter_client import code_session
      with code_session("us-east-1") as ci:   # starts a managed sandbox, stops on exit
          resp = ci.execute_code("print(2+2)")            # language="python" default
    * Default sandbox identifier: "aws.codeinterpreter.v1"; default session timeout 900s.
    * execute_code(code, language="python", clear_context=False) -> dict. The result is
      in resp["stream"]; each event's ["result"]["structuredContent"] is
      {stdout, stderr, exitCode, executionTime}. ["result"]["content"][0]["text"] is
      the same text. (invoke("executeCode", {...}) is the low-level form.)
    * execute_command(cmd) runs a shell command; install_packages([...]) pip-installs.
    * The kernel + filesystem PERSIST across calls within one session; clear_context=True
      wipes the kernel state. The context manager calls stop() on exit (auto-teardown).

Usage:
    AWS_PROFILE=<admin-profile> uv run python 16_agentcore_tools/code_interpreter.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from bedrock_agentcore.tools.code_interpreter_client import code_session

from strands import Agent, tool

from tools import get_model  # importing this loads LESSON_DOTENV (for the Gemini key)

# GOTCHA: LESSON_DOTENV (the LESSON_DOTENV file) may inject static AWS_* keys that override the
# SSO profile and cause InvalidClientTokenId. When an AWS_PROFILE is set, drop those
# static keys so the profile's (SSO) credentials win. Must run AFTER get_model import.
if os.environ.get("AWS_PROFILE"):
    for _k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        os.environ.pop(_k, None)

REGION = "us-east-1"


def result_of(resp: dict) -> dict:
    """Pull the {stdout, stderr, exitCode, executionTime} out of an execute response."""
    for ev in (resp or {}).get("stream", []):
        sc = ev.get("result", {}).get("structuredContent")
        if sc is not None:
            return sc
    return {}


def preflight() -> bool:
    try:
        ident = boto3.client("sts", region_name=REGION).get_caller_identity()
        print(f"  authenticated as {ident['Arn'].split('/')[-1]} (acct {ident['Account']})")
        return True
    except Exception as e:
        print(f"  AWS credentials unavailable: {str(e)[:90]}")
        print("  -> run:  aws sso login --profile <your-admin-profile>")
        return False


# ---------------------------------------------------------------------------
# ITERATION 1: execute code -> structured result
# ---------------------------------------------------------------------------
def iteration_1_execute(ci) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: execute code -> structured result (stdout/stderr/exitCode)")
    print("=" * 70)
    r = result_of(ci.execute_code("print(sum(range(11)))"))
    print(f"  code: print(sum(range(11)))  -> stdout={r.get('stdout')!r} exitCode={r.get('exitCode')}")
    assert r.get("stdout", "").strip() == "55" and r.get("exitCode") == 0
    # An error is reported structurally too, not as a Python exception in YOUR process.
    err = result_of(ci.execute_code("1/0"))
    print(f"  code: 1/0  -> exitCode={err.get('exitCode')} stderr~={err.get('stderr','')[:40]!r}")
    assert err.get("exitCode") != 0 and "ZeroDivisionError" in err.get("stderr", "")
    print("  OK: results are structured; a sandbox error is data, not a crash in your process.")


# ---------------------------------------------------------------------------
# ITERATION 2: the session is stateful
# ---------------------------------------------------------------------------
def iteration_2_stateful(ci) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: the kernel is STATEFUL across calls (clear_context resets)")
    print("=" * 70)
    ci.execute_code("secret = 6 * 7")                       # define in call 1
    r = result_of(ci.execute_code("print(secret)"))          # use in call 2
    print(f"  defined 'secret' in one call, read it in the next -> {r.get('stdout','').strip()!r}")
    assert r.get("stdout", "").strip() == "42", "state should persist across calls"

    after = result_of(ci.execute_code("print(secret)", clear_context=True))
    print(f"  same call with clear_context=True -> exitCode={after.get('exitCode')} "
          f"stderr~={after.get('stderr','')[:30]!r}")
    assert after.get("exitCode") != 0, "clear_context should wipe the kernel (NameError)"
    print("  OK: one persistent kernel per session; clear_context=True wipes it.")


# ---------------------------------------------------------------------------
# ITERATION 3: shell + a persistent filesystem
# ---------------------------------------------------------------------------
def iteration_3_shell_fs(ci) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: shell commands + a filesystem that persists in-session")
    print("=" * 70)
    ci.execute_command("echo 'hello from the shell' > /tmp/note.txt")
    r = result_of(ci.execute_code("print(open('/tmp/note.txt').read().strip())"))
    print(f"  wrote a file via shell, read it via Python -> {r.get('stdout','').strip()!r}")
    assert r.get("stdout", "").strip() == "hello from the shell"

    # Best-effort package install (needs the sandbox to have network egress).
    try:
        inst = result_of(ci.install_packages(["cowsay"]))
        used = result_of(ci.execute_code("import cowsay; cowsay.cow('moo'); print('cowsay-ok')"))
        ok = "cowsay-ok" in used.get("stdout", "")
        print(f"  install_packages(['cowsay']) -> import works: {ok}")
    except Exception as e:
        print(f"  install_packages note (egress may be restricted): {str(e)[:60]}")
    print("  OK: real shell + filesystem; the sandbox is a machine, not a calculator.")


# ---------------------------------------------------------------------------
# ITERATION 4: wire the sandbox to a Strands agent
# ---------------------------------------------------------------------------
def iteration_4_agent(ci) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 4: give a Strands agent a sandboxed run_python tool")
    print("=" * 70)

    @tool
    def run_python(code: str) -> str:
        """Execute Python in a secure sandbox and return its stdout (or stderr)."""
        sc = result_of(ci.execute_code(code))
        return sc.get("stdout") or sc.get("stderr") or "(no output)"

    agent = Agent(
        model=get_model("gemini-2.5-flash"),
        tools=[run_python],
        system_prompt="To compute anything, WRITE and RUN Python via run_python. "
                      "Print the answer. Then state it in one short sentence.",
        callback_handler=None,
    )
    answer = str(agent("What is the 20th Fibonacci number (fib(1)=fib(2)=1)? Compute it with code."))
    print(f"  agent answer: {answer.strip()[:70]!r}")
    assert "6765" in answer, "fib(20)=6765 — the agent should compute it in the sandbox"
    print("  OK: the agent solved the task by running code it wrote in the managed sandbox.")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L72 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. One context manager
   with code_session("us-east-1") as ci: ci.execute_code("...")
   Starts a managed, isolated sandbox (kernel + filesystem) and stops it on exit.

2. Structured results
   resp["stream"][.]["result"]["structuredContent"] = {stdout, stderr, exitCode,
   executionTime}. A sandbox error is DATA (exitCode != 0), not an exception in
   your process — safe to hand an LLM.

3. Stateful, with a real filesystem
   The kernel persists variables across calls (clear_context=True resets it);
   execute_command gives you a shell; install_packages pip-installs (needs egress).

4. The point: safe agentic code-run
   Back an agent's run_python tool with the sandbox and it can write+run code to
   solve tasks WITHOUT touching your machine. vs L24 (local subprocess/Docker):
   same idea, but AWS-isolated and managed.

5. Sibling: L73 Browser
   bedrock_agentcore.tools.browser_client gives a managed headless Chrome over CDP
   — the same "managed tool for an agent" pattern, for the web instead of a REPL.
""")


def main() -> None:
    print("AgentCore Code Interpreter — L72")
    if not preflight():
        sys.exit(1)
    with code_session(REGION) as ci:
        print(f"  sandbox session: {ci.session_id}")
        iteration_1_execute(ci)
        iteration_2_stateful(ci)
        iteration_3_shell_fs(ci)
        iteration_4_agent(ci)
    print("\n  (code_session context exited -> sandbox stopped/torn down)")
    summary()


if __name__ == "__main__":
    main()
