"""L94 probe: settle the L61 count_tokens discrepancy.

L61 (2026-06-02, SDK 1.42) recorded: "docstring claims tiktoken cl100k_base but the v1.42 path is
char heuristic (ceil(chars/4))". The v1.42.0 tag source ALREADY had tiktoken-first with chars/4
fallback, so the recorded claim looks like an environment artifact. This probe measures both paths
at runtime on the installed SDK:

  mode=normal   -> tiktoken importable (it is a repo dependency)
  mode=blocked  -> tiktoken import blocked via sys.modules poisoning (child process)

For each L61-style test string (code / CJK / punctuation / plain), prints the SDK's count, the
true tiktoken cl100k_base length, and ceil(chars/4), and states which one the SDK count matches.
"""

import asyncio
import math
import subprocess
import sys

TESTS = {
    "plain": "The quick brown fox jumps over the lazy dog near the river bank today.",
    "code": "def f(x):\n    return {k: v for k, v in x.items() if v is not None}\n" * 3,
    "cjk": "东京は日本の首都であり、世界最大の都市圏を形成している。" * 3,
    "punct": "!@#$%^&*()_+-=[]{}|;':\",./<>?`~" * 5,
}


def run_probe() -> None:
    import tiktoken

    from strands.models.openai import OpenAIModel

    enc = tiktoken.get_encoding("cl100k_base")
    model = OpenAIModel(model_id="probe", client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"})

    for name, text in TESTS.items():
        sdk = asyncio.run(model.count_tokens([{"role": "user", "content": [{"text": text}]}]))
        true_tt = len(enc.encode(text))
        heur = math.ceil(len(text) / 4)
        # sdk counts the whole message structure; compare against per-text baselines directionally
        closest = "tiktoken" if abs(sdk - true_tt) < abs(sdk - heur) else "chars/4"
        print(f"{name:6s} sdk={sdk:4d}  tiktoken(text)={true_tt:4d}  chars/4(text)={heur:4d}  closest={closest}")


def run_blocked() -> None:
    sys.modules["tiktoken"] = None  # poison: import raises ImportError -> SDK must fall back
    run_probe_no_tt()


def run_probe_no_tt() -> None:
    import math

    from strands.models.openai import OpenAIModel

    model = OpenAIModel(model_id="probe", client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"})
    for name, text in TESTS.items():
        sdk = asyncio.run(model.count_tokens([{"role": "user", "content": [{"text": text}]}]))
        heur = math.ceil(len(text) / 4)
        print(f"{name:6s} sdk={sdk:4d}  chars/4(text)={heur:4d}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    if mode == "normal":
        print("== mode=normal (tiktoken importable) ==")
        run_probe()
        print("\n== mode=blocked (child process, tiktoken poisoned) ==")
        out = subprocess.run(
            [sys.executable, __file__, "blocked"], capture_output=True, text=True, timeout=120
        )
        print(out.stdout, end="")
        if out.returncode != 0:
            print("child stderr:", out.stderr[-500:])
            raise SystemExit(1)
    elif mode == "blocked":
        run_blocked()
