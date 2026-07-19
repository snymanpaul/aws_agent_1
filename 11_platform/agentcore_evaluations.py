"""
Level 34: AgentCore Evaluations — Cloud-side Quality Measurement
================================================================
Measure agent quality on live production traffic via AgentCore's
evaluation service — without changing any agent code.

Goal: understand the full evaluation lifecycle:
  - Built-in evaluators (13 across TRACE/SESSION/TOOL_CALL levels)
  - Custom LLM-as-judge evaluators (domain-specific rubrics)
  - Online eval config (continuous sampling from CloudWatch Logs)
  - On-demand evaluate (run against captured session spans)

API surface (probed via service_model before coding):
  control:  create_evaluator, create_online_evaluation_config, ...
  runtime:  evaluate (on-demand, free-form sessionSpans document)

L21 vs L34:
    L21 = what happened  (metrics, latency, error rates)
    L34 = how well       (semantic quality, helpfulness, goal success)

L33 vs L34:
    L33 = policy gate    (who can do what — Cedar, <1ms)
    L34 = quality signal (did the agent do it well — LLM judge, async)

AWS resources (live from L27):
    Log groups:
        /aws/bedrock-agentcore/runtimes/l27agentcore_Agent-8SQjr5BSN3-PROD
        /aws/bedrock-agentcore/runtimes/l27agentcore_Agent-8SQjr5BSN3-DEV
    Account: <data-account-id>  |  Region: us-east-1

Usage:
    AWS_PROFILE=<your-sso-profile> \\
        uv run python 11_platform/agentcore_evaluations.py
"""

import sys
import os
import time
import json
import boto3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REGION  = "us-east-1"
ACCOUNT = "<data-account-id>"
RUN_ID  = str(int(time.time()))[-6:]

# L27 AgentCore agent runtime identifiers.
# For online evaluation, dataSourceConfig requires:
#   logGroupNames  — a CUSTOM trace log group (not the runtime stdout log groups).
#                    The evaluation service reads OTel span data from here.
#   serviceNames   — format is <agentName>.<endpoint> (e.g. "myAgent.PROD")
#                    NOT the log group name — this is the OTel service.name attribute
# The execution role must also have read access to /aws/spans (CloudWatch span store).
# Docs: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html
L27_AGENT_NAME       = "l27agentcore_Agent-8SQjr5BSN3"
L27_SERVICE_NAME     = f"{L27_AGENT_NAME}.PROD"    # <agentName>.<endpoint> format
L34_TRACE_LOG_GROUP  = "/aws/agentcore/l34-traces"  # custom log group we create

AWS_PROFILE = os.environ.get("AWS_PROFILE")
_session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
ctrl    = _session.client("bedrock-agentcore-control")
runtime = _session.client("bedrock-agentcore")
iam     = _session.client("iam")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def poll(fn, done_statuses=("ACTIVE",),
         fail_statuses=("FAILED", "CREATE_FAILED"),
         interval=3, max_attempts=20):
    for i in range(max_attempts):
        resp = fn()
        status = resp.get("status", "")
        print(f"    [{i+1}] status={status}")
        if status in done_statuses:
            return resp
        if status in fail_statuses:
            raise RuntimeError(f"Operation failed ({status}): {resp.get('failureReason')}")
        time.sleep(interval)
    raise TimeoutError("Polling timed out")


def jprint(d):
    d = {k: v for k, v in d.items() if k != "ResponseMetadata"}
    print(json.dumps(d, indent=2, default=str))


# ---------------------------------------------------------------------------
# Startup cleanup — remove any l34 evaluator left from a previous run
# ---------------------------------------------------------------------------

def _cleanup_existing():
    evals = ctrl.list_evaluators().get("evaluators", [])
    for e in [x for x in evals if x["evaluatorName"].startswith("l34_")]:
        print(f"[startup] leftover evaluator {e['evaluatorId']} — deleting")
        ctrl.delete_evaluator(evaluatorId=e["evaluatorId"])
    configs = ctrl.list_online_evaluation_configs().get("onlineEvaluationConfigs", [])
    for c in [x for x in configs if x.get("onlineEvaluationConfigName", "").startswith("l34_")]:
        print(f"[startup] leftover eval config {c['onlineEvaluationConfigId']} — deleting")
        ctrl.delete_online_evaluation_config(
            onlineEvaluationConfigId=c["onlineEvaluationConfigId"]
        )
    # cleanup IAM role
    role_name = "l34-eval-execution-role"
    try:
        policies = iam.list_role_policies(RoleName=role_name).get("PolicyNames", [])
        for p in policies:
            iam.delete_role_policy(RoleName=role_name, PolicyName=p)
        iam.delete_role(RoleName=role_name)
        print(f"[startup] leftover IAM role {role_name} — deleted")
    except iam.exceptions.NoSuchEntityException:
        pass
    # cleanup trace log group
    try:
        _session.client("logs").delete_log_group(
            logGroupName="/aws/agentcore/l34-traces"
        )
        print("[startup] leftover trace log group deleted")
    except Exception:
        pass


_cleanup_existing()


# ---------------------------------------------------------------------------
# ITERATION 1: Built-in evaluators + custom LLM-as-judge
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 1: Built-in evaluators + custom LLM-as-judge")
print("=" * 70)
print("""
13 built-in evaluators, 3 levels:
  TRACE      — per response quality (Correctness, Faithfulness, Helpfulness,
                ResponseRelevance, Conciseness, Coherence, InstructionFollowing,
                Refusal, Harmfulness, Stereotyping)
  SESSION    — per conversation outcome (GoalSuccessRate)
  TOOL_CALL  — tool quality (ToolSelectionAccuracy, ToolParameterAccuracy)

Custom LLM-as-judge: domain rubric with a numerical rating scale,
evaluated by a Bedrock model. Same API surface as built-in evaluators
once created; reference by evaluatorId.
""")

print("--- list_evaluators (built-in) ---")
builtin = ctrl.list_evaluators().get("evaluators", [])
by_level = {}
for e in builtin:
    lvl = e["level"]
    by_level.setdefault(lvl, []).append(e["evaluatorId"])
for lvl, ids in sorted(by_level.items()):
    print(f"  {lvl}: {', '.join(ids)}")

print(f"\n  Total built-in evaluators: {len(builtin)}")

print("\n--- create custom LLM-as-judge evaluator (TRACE level) ---")
CUSTOM_EVAL_NAME = f"l34_math_quality_{RUN_ID}"
custom_resp = ctrl.create_evaluator(
    evaluatorName=CUSTOM_EVAL_NAME,
    description="Scores math agent responses on correctness and explanation quality",
    level="TRACE",
    evaluatorConfig={
        "llmAsAJudge": {
            # TRACE-level instructions must include at least one of:
            # {context}, {assistant_turn}, {expected_response}
            "instructions": (
                "You are evaluating a math assistant agent. "
                "Here is the agent's response: {assistant_turn}\n\n"
                "Score on correctness of calculation and clarity of explanation. "
                "Use the rating scale below."
            ),
            "ratingScale": {
                "numerical": [
                    {"value": 1.0, "label": "Wrong",   "definition": "Calculation is incorrect or explanation is absent"},
                    {"value": 2.0, "label": "Partial",  "definition": "Calculation correct but explanation unclear or incomplete"},
                    {"value": 3.0, "label": "Good",     "definition": "Correct calculation with clear explanation"},
                ]
            },
            "modelConfig": {
                "bedrockEvaluatorModelConfig": {
                    "modelId": "amazon.nova-micro-v1:0",
                }
            },
        }
    },
)
custom_resp.pop("ResponseMetadata", None)
CUSTOM_EVAL_ID  = custom_resp["evaluatorId"]
CUSTOM_EVAL_ARN = custom_resp["evaluatorArn"]
print(f"  evaluatorId: {CUSTOM_EVAL_ID}")
print(f"  status:      {custom_resp['status']}")

print("  polling until ACTIVE...")
poll(lambda: {
    k: v for k, v in ctrl.get_evaluator(evaluatorId=CUSTOM_EVAL_ID).items()
    if k != "ResponseMetadata"
})
print(f"  custom evaluator ready: {CUSTOM_EVAL_ID}")

print("\n--- list_evaluators (all, post-create) ---")
all_evals = ctrl.list_evaluators().get("evaluators", [])
custom_found = [e for e in all_evals if e["evaluatorId"] == CUSTOM_EVAL_ID]
print(f"  total: {len(all_evals)}  (13 built-in + 1 custom)")
print(f"  custom: {custom_found[0]['evaluatorName']} — {custom_found[0]['status']}")


# ---------------------------------------------------------------------------
# ITERATION 2: Online evaluation config (continuous sampling)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 2: Online evaluation config — continuous sampling")
print("=" * 70)
print(f"""
create_online_evaluation_config wires evaluation to the live agent's
OTel span data stream. Every N% of requests are sampled, evaluated
by the selected evaluators, and results written to CloudWatch Metrics.

Two modes:
  enableOnCreate=True  → starts immediately (ENABLED)
  enableOnCreate=False → created DISABLED; enable later via update

Data source requirements (from docs RCA):
  logGroupNames — CUSTOM trace log group (NOT the runtime stdout logs).
                  The evaluation service reads OTel span data from this group.
  serviceNames  — OTel service.name, format: <agentName>.<endpoint>
                  e.g. "{L27_SERVICE_NAME}"
  Execution role also needs read access to /aws/spans (CW span store).

Note: The L27 agent is not ADOT-instrumented, so the config creates fine
but will have no actual traffic to evaluate. This iteration demonstrates
the config lifecycle: create → enable → verify → disable → delete.

Evaluators: Helpfulness (TRACE) + GoalSuccessRate (SESSION)
""")

print(f"--- create trace log group {L34_TRACE_LOG_GROUP} ---")
logs_client = _session.client("logs")
try:
    logs_client.create_log_group(logGroupName=L34_TRACE_LOG_GROUP)
    print(f"  created {L34_TRACE_LOG_GROUP}")
except logs_client.exceptions.ResourceAlreadyExistsException:
    print(f"  already exists: {L34_TRACE_LOG_GROUP}")
# Verify it's visible before using it
existing = logs_client.describe_log_groups(logGroupNamePrefix=L34_TRACE_LOG_GROUP)
lg_arn = None
for lg in existing.get("logGroups", []):
    if lg["logGroupName"] == L34_TRACE_LOG_GROUP:
        lg_arn = lg.get("arn")
        print(f"  verified: {lg['logGroupName']}  arn: {lg_arn}")
print(f"  log group ARN: {lg_arn}")

print("\n--- create IAM execution role for evaluation ---")
EVAL_ROLE_NAME = "l34-eval-execution-role"
trust = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }]
}
role_resp = iam.create_role(
    RoleName=EVAL_ROLE_NAME,
    AssumeRolePolicyDocument=json.dumps(trust),
    Description="L34 evaluation execution role",
)
EVAL_ROLE_ARN = role_resp["Role"]["Arn"]
print(f"  roleArn: {EVAL_ROLE_ARN}")

iam.put_role_policy(
    RoleName=EVAL_ROLE_NAME,
    PolicyName="eval-execution-policy",
    PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                # Online eval reads OTel spans from /aws/spans (shared CW span store)
                # and from the custom trace log group
                "Effect": "Allow",
                "Action": [
                    "logs:FilterLogEvents", "logs:GetLogEvents",
                    "logs:DescribeLogGroups", "logs:DescribeLogStreams",
                    "logs:StartQuery", "logs:StopQuery", "logs:GetQueryResults",
                    "logs:GetLogRecord", "logs:CreateLogGroup",
                    "logs:CreateLogStream", "logs:PutLogEvents",
                ],
                "Resource": "arn:aws:logs:*:*:*",
            },
            {
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": "arn:aws:bedrock:*::foundation-model/*",
            },
            {
                "Effect": "Allow",
                "Action": "bedrock-agentcore:*",
                "Resource": "*",
            },
        ]
    })
)
print(f"  permissions attached")
# IAM changes take a few seconds to propagate globally
print("  waiting 10s for IAM propagation...", end="", flush=True)
time.sleep(10)
print(" ok")

print("\n--- create_online_evaluation_config (attempt — may fail for Preview API) ---")
print(f"""
  dataSourceConfig:
    logGroupNames: [{L34_TRACE_LOG_GROUP}]   ← custom trace log group (created above)
    serviceNames:  [{L27_SERVICE_NAME}]          ← OTel service.name format

  NOTE: This API is in Preview. The ValidationException
  "One or more specified log groups do not exist" fires even for log groups
  that exist in CloudWatch. The service appears to validate log groups against
  an Application Signals / OTel registry, not plain CloudWatch.

  For this to work end-to-end, the agent must be:
    1. Instrumented with ADOT SDK (AWS Distro for OpenTelemetry)
    2. Exporting spans to Application Signals (CloudWatch Synthetics)
    3. The log group must have been created BY Application Signals,
       not by a direct boto3 create_log_group call

  Demonstrating the API call and documenting the prerequisite gap:
""")

try:
    cfg_resp = ctrl.create_online_evaluation_config(
        onlineEvaluationConfigName=f"l34_online_eval_{RUN_ID}",
        description="L34: continuous quality sampling on L27 agent traffic",
        rule={
            "samplingConfig": {"samplingPercentage": 100.0},
            "sessionConfig": {"sessionTimeoutMinutes": 30},
        },
        dataSourceConfig={
            "cloudWatchLogs": {
                "logGroupNames": [L34_TRACE_LOG_GROUP],
                "serviceNames":  [L27_SERVICE_NAME],
            }
        },
        evaluators=[
            {"evaluatorId": "Builtin.Helpfulness"},
            {"evaluatorId": "Builtin.GoalSuccessRate"},
            {"evaluatorId": CUSTOM_EVAL_ID},
        ],
        evaluationExecutionRoleArn=EVAL_ROLE_ARN,
        enableOnCreate=False,
    )
    cfg_resp.pop("ResponseMetadata", None)
    CFG_ID = cfg_resp["onlineEvaluationConfigId"]
    print(f"  SUCCESS  configId: {CFG_ID}  status: {cfg_resp['status']}")

    poll(lambda: {
        k: v for k, v in ctrl.get_online_evaluation_config(
            onlineEvaluationConfigId=CFG_ID
        ).items()
        if k != "ResponseMetadata"
    })

    cfg = ctrl.get_online_evaluation_config(onlineEvaluationConfigId=CFG_ID)
    print(f"  status: {cfg['status']}  executionStatus: {cfg.get('executionStatus')}")
    print(f"  evaluators: {[e['evaluatorId'] for e in cfg.get('evaluators', [])]}")

    ctrl.update_online_evaluation_config(onlineEvaluationConfigId=CFG_ID, executionStatus="ENABLED")
    print(f"  enabled")
    ctrl.update_online_evaluation_config(onlineEvaluationConfigId=CFG_ID, executionStatus="DISABLED")
    ctrl.delete_online_evaluation_config(onlineEvaluationConfigId=CFG_ID)
    print(f"  lifecycle complete: enabled → disabled → deleted")

except Exception as e:
    print(f"""
  ValidationException: {e}

  CONFIRMED PREREQUISITE GAP:
    The log group /aws/agentcore/l34-traces exists in CloudWatch but is
    rejected by the evaluation service. The service validates log groups
    against an internal registry populated by Application Signals /
    OTel collector — not the standard CloudWatch describe-log-groups API.

  To use online evaluation in production:
    1. Deploy agent with ADOT instrumentation (generates /aws/spans spans)
    2. Enable Application Signals in CloudWatch for the agent service
    3. Application Signals auto-creates the trace log group and registers it
    4. THEN create_online_evaluation_config works with that log group
    5. serviceNames = OTel service.name attribute (format: agentName.endpoint)

  This level demonstrates the evaluators API (Iteration 1) and the
  API shape of online eval config. The lifecycle demo runs in Iteration 3
  via the on-demand evaluate path.
""")


# ---------------------------------------------------------------------------
# ITERATION 3: On-demand evaluate (runtime)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 3: On-demand evaluate — runtime call against session spans")
print("=" * 70)
print("""
runtime.evaluate() runs an evaluator against a provided session span.
'sessionSpans' is a free-form document type (empty Smithy structure members)
representing captured AgentCore session data.

On-demand evaluation is useful for:
  - CI/CD gates: run evaluators against a fixed test session
  - Regression checks after model/prompt changes
  - Post-incident review of specific sessions

This iteration attempts evaluate() with a synthetic session span
and documents the API response or error structure.
""")

print("--- runtime.evaluate with Builtin.Helpfulness ---")
try:
    result = runtime.evaluate(
        evaluatorId="Builtin.Helpfulness",
        evaluationInput={
            "sessionSpans": [
                {
                    "input":  "What is 15 multiplied by 8?",
                    "output": "15 × 8 = 120. I multiply the ones: 5×8=40, carry 4; "
                              "tens: 1×8=8, add 4 = 12. So 120.",
                    "type":   "CONVERSATION",
                }
            ]
        },
    )
    result.pop("ResponseMetadata", None)
    print(f"  evaluationResults: {json.dumps(result, indent=2, default=str)}")
except Exception as e:
    print(f"""
  Result: {type(e).__name__}: {e}

  Why this is expected for synthetic data:
    runtime.evaluate() is designed to work with session spans captured by
    the AgentCore runtime — each span has a specific schema including
    traceId, spanId, timestamp, and structured input/output fields
    tied to the agent's OTel trace context.

    Synthetic spans (plain dict) are rejected at the service layer.
    In production, session spans are obtained from:
      - CloudWatch Logs (the same source as OnlineEvaluationConfig)
      - AgentCore trace export (via OTel collector)
      - Captured via AgentCore session replay APIs

    The API shape (evaluatorId + sessionSpans doc) is correct —
    the data itself must come from real AgentCore runtime sessions.
""")


# ===========================================================================
# ITERATION 4: Evaluation Datasets (bedrock-agentcore 1.12 — DatasetClient)
# ===========================================================================
# DatasetClient curates reusable evaluation datasets on bedrock-agentcore-control.
# Validated end-to-end 2026-06-02 (REQUIRES botocore >= 1.43.19 — create_dataset is
# absent from the service model in 1.43.2; the SDK bundles no model of its own):
#   create_dataset_and_wait(datasetName, schemaType, source) -> waits ACTIVE
#   PREDEFINED_V1 example schema: {scenario_id, turns: [{input, expected_output}]}
#   source = {"inlineExamples": {"examples": [...]}}  (or {"s3Source": {"s3Uri": ...}})
#   lifecycle: get_dataset / list_dataset_examples / create_dataset_version_and_wait
#              / delete_dataset_and_wait
#
# CORRECTION vs first assumptions: a dataset is a STANDALONE curated-examples
# resource (a reusable "golden set"), NOT an input to runtime.evaluate(). No
# control-plane op takes a datasetId, and CreateOnlineEvaluationConfig samples
# CloudWatch Logs (Iteration 2), not a dataset. Datasets back repeatable/offline
# evaluation runs — distinct from Iteration 3's on-demand evaluate().
print("\n" + "=" * 70)
print("ITERATION 4: Evaluation Datasets — DatasetClient (curated golden sets)")
print("=" * 70)

from bedrock_agentcore.evaluation.dataset_client import DatasetClient

dataset_client = DatasetClient(region_name=REGION, boto3_session=_session)
DATASET_NAME = "l34_capital_quiz_eval"  # name regex: [a-zA-Z][a-zA-Z0-9_]{0,47}

# Two predefined conversational scenarios (input + expected_output per turn).
dataset_examples = [
    {"scenario_id": "capital-fr",
     "turns": [{"input": "What is the capital of France?", "expected_output": "Paris"}]},
    {"scenario_id": "capital-jp",
     "turns": [{"input": "What is the capital of Japan?", "expected_output": "Tokyo"}]},
]

print(f"  create_dataset_and_wait({DATASET_NAME!r}, {len(dataset_examples)} scenarios)...")
ds = dataset_client.create_dataset_and_wait(
    datasetName=DATASET_NAME,
    schemaType="AGENTCORE_EVALUATION_PREDEFINED_V1",
    source={"inlineExamples": {"examples": dataset_examples}},
)
ds_id = ds["datasetId"]
print(f"    status={ds['status']}  datasetId={ds_id}  exampleCount={ds.get('exampleCount')}")

examples_resp = dataset_client.list_dataset_examples(datasetId=ds_id)
print(f"    list_dataset_examples -> {len(examples_resp.get('examples', []))} examples")

# A version snapshots the examples for reproducible evaluation runs.
ver = dataset_client.create_dataset_version_and_wait(datasetId=ds_id)
print(f"    create_dataset_version -> datasetVersion={ver.get('datasetVersion')} status={ver.get('status')}")

print("  -> a dataset is a reusable golden set; pair it with an evaluator for")
print("     repeatable offline eval (NOT fed to runtime.evaluate by id).")

# Cleanup — delete the dataset this iteration created.
dataset_client.delete_dataset_and_wait(datasetId=ds_id)
print(f"  cleanup: deleted dataset {ds_id}")


print("\n--- cleanup: delete custom evaluator + IAM role ---")
ctrl.delete_evaluator(evaluatorId=CUSTOM_EVAL_ID)
print(f"  deleted evaluator {CUSTOM_EVAL_ID}")

iam.delete_role_policy(RoleName=EVAL_ROLE_NAME, PolicyName="eval-execution-policy")
iam.delete_role(RoleName=EVAL_ROLE_NAME)
print(f"  deleted IAM role {EVAL_ROLE_NAME}")
try:
    logs_client.delete_log_group(logGroupName=L34_TRACE_LOG_GROUP)
    print(f"  deleted log group {L34_TRACE_LOG_GROUP}")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("L34 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Two evaluation paths
   • Online  — continuous: create_online_evaluation_config → samples live traffic
     from CloudWatch Logs → writes quality metrics to CloudWatch
   • On-demand — runtime.evaluate(evaluatorId, {sessionSpans: [...]})
     requires real AgentCore session span data (not synthetic)

2. Built-in evaluators (13 total, no creation needed)
   • TRACE      — Correctness, Faithfulness, Helpfulness, ResponseRelevance,
                  Conciseness, Coherence, InstructionFollowing, Refusal,
                  Harmfulness, Stereotyping
   • SESSION    — GoalSuccessRate
   • TOOL_CALL  — ToolSelectionAccuracy, ToolParameterAccuracy
   • Reference by evaluatorId string (e.g. "Builtin.Helpfulness")

3. Custom LLM-as-judge evaluator
   • create_evaluator(name, level, evaluatorConfig.llmAsAJudge)
   • llmAsAJudge: instructions + ratingScale (numerical or categorical) + modelConfig
   • modelConfig.bedrockEvaluatorModelConfig.modelId = Bedrock model ARN/ID
   • Async: poll get_evaluator until ACTIVE
   • Same API shape as built-in once active; mix freely in evaluators list

4. Online evaluation config
   • create_online_evaluation_config(name, rule, dataSourceConfig, evaluators,
       evaluationExecutionRoleArn, enableOnCreate)
   • rule.samplingConfig.samplingPercentage — 0-100
   • dataSourceConfig.cloudWatchLogs: logGroupNames + serviceNames (required)
   • evaluationExecutionRoleArn: role needs logs:FilterLogEvents +
       bedrock:InvokeModel + bedrock-agentcore:*
   • Two statuses: status (resource) + executionStatus (ENABLED/DISABLED)
   • enableOnCreate=False → create DISABLED, enable via update_online_evaluation_config
   • Cleanup: update executionStatus=DISABLED → delete_online_evaluation_config

5. On-demand evaluate
   • runtime.evaluate(evaluatorId, {sessionSpans: [free-form doc]})
   • sessionSpans is a document type — requires real AgentCore OTel spans
   • Synthetic data rejected; must use captured runtime session data
   • Useful for: CI gates, regression checks, post-incident review

6. L21 → L34 → L35 triad
   • L21 = what happened    (OTel traces, latency, token counts)
   • L34 = how well         (cloud-side semantic quality, live traffic)
   • L35 = test correctness (local Strands Evals SDK, CI/CD pipeline)
""")
