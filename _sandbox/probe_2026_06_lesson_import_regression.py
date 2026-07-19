"""Probe: offline lesson-import regression for the 2026-06 SDK upgrade.

The dep bump (strands 1.38->1.42, tools 0.5.2->0.7.0, agentcore 1.8->1.12,
fastapi/starlette transitive) could break any lesson that imports an SDK symbol
whose name/location changed. pytest gives no signal here (no collectable tests),
and the runtime spot-runs need the LiteLLM proxy / AWS. So this is the strongest
*offline* regression available: import every ``if __name__ == "__main__"``-guarded
lesson module under the new SDK and report which fail to import.

Guarded modules are import-safe by construction (their work runs only under the
guard), so importing them executes only module-level imports + def/class bodies —
exactly the surface a dependency break would hit. Each module is loaded under a
unique synthetic name to avoid basename collisions, in its own try/except so one
break never masks the rest.

    uv run python _sandbox/probe_2026_06_lesson_import_regression.py

Exit 0 iff every guarded lesson imports cleanly under the upgraded SDK.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = '__name__ == "__main__"'
SKIP_DIRS = {"__pycache__", "test", "cdk.out", "_sandbox"}

# Discover guarded lesson files inside the numbered tier dirs only.
lesson_files: list[pathlib.Path] = []
for tier in sorted(ROOT.glob("[0-9][0-9]_*")):
    if not tier.is_dir():
        continue
    for py in tier.rglob("*.py"):
        if any(part in SKIP_DIRS for part in py.parts):
            continue
        if py.name.startswith("test_"):
            continue
        try:
            if GUARD in py.read_text(encoding="utf-8", errors="ignore"):
                lesson_files.append(py)
        except OSError:
            pass

# Ensure local packages (e.g. `tools`) resolve during import.
sys.path.insert(0, str(ROOT))

passed: list[str] = []
failed: list[tuple[str, str]] = []

print(f"{'='*78}\n2026-06 lesson-import regression ({len(lesson_files)} guarded modules)\n{'='*78}", flush=True)
for i, py in enumerate(sorted(lesson_files), 1):
    rel = py.relative_to(ROOT).as_posix()
    mod_name = "lesson_" + rel.replace("/", "_").removesuffix(".py")
    try:
        spec = importlib.util.spec_from_file_location(mod_name, py)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)  # runs imports + defs; guard prevents main()
        passed.append(rel)
        print(f"[{i:>3}/{len(lesson_files)}] ok   {rel}", flush=True)
    except BaseException as exc:  # noqa: BLE001 - capture every failure mode
        tb = traceback.format_exc().strip().splitlines()
        # surface the SDK-relevant frame if present
        sdk_line = next(
            (ln.strip() for ln in tb if "strands" in ln or "bedrock_agentcore" in ln),
            tb[-1] if tb else "",
        )
        failed.append((rel, f"{type(exc).__name__}: {exc} | {sdk_line}"))
        print(f"[{i:>3}/{len(lesson_files)}] FAIL {rel}\n        {failed[-1][1]}", flush=True)

print(f"{'-'*78}\n{len(passed)}/{len(lesson_files)} imported cleanly; {len(failed)} failed")

if failed:
    raise SystemExit(f"{len(failed)} lesson(s) fail to import under upgraded SDK")
print("REGRESSION CLEAN — every guarded lesson imports under strands 1.42 / agentcore 1.12.")
