"""Quality gates for agent-built code.

Three gates, all pure standard library:

- ``no_sim_check``      flags substituted integrations: code that fabricates a success
                        for a call it could have made.
- ``check_no_aws_ids``  blocks AWS account identifiers from entering tracked text.
- ``eval_harness``      multi-run evaluation with Wilson intervals, permutation
                        significance, and a pass/fail gate against a frozen baseline.

A fourth, ``ship_gate``, composes the harness into one auditable GO/NO-GO verdict over
real agent runs. It needs a framework and it spends money, so it lives behind an extra::

    pip install 'agent-build-gates[strands]'

``ship_gate`` is deliberately not re-exported here, so importing this package never
pulls in the optional dependency. Import it directly when you want it::

    from agent_build_gates.ship_gate import ship_gate
"""

from . import check_no_aws_ids, eval_harness, no_sim_check
from .eval_harness import Case, gate, load_baseline, perm_test, quality, run_suite, save_baseline, wilson

__version__ = "0.1.0"

__all__ = [
    "no_sim_check",
    "check_no_aws_ids",
    "eval_harness",
    "Case",
    "run_suite",
    "gate",
    "quality",
    "wilson",
    "perm_test",
    "save_baseline",
    "load_baseline",
]
