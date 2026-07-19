"""Probe: full DatasetClient lifecycle for L34 Iteration 4 (self-cleaning).

Verifies create -> get -> list examples -> version -> delete against live AWS.
PREDEFINED_V1 example schema (discovered empirically): {scenario_id, turns:[{input, expected_output}]}.
    AWS_PROFILE=... uv run python _sandbox/probe_l34_dataset_create.py
"""
import os
import boto3
from bedrock_agentcore.evaluation.dataset_client import DatasetClient

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name="us-east-1")
client = DatasetClient(region_name="us-east-1", boto3_session=session)

examples = [
    {"scenario_id": "capital-fr",
     "turns": [{"input": "What is the capital of France?", "expected_output": "Paris"}]},
    {"scenario_id": "capital-jp",
     "turns": [{"input": "What is the capital of Japan?", "expected_output": "Tokyo"}]},
]

ds = client.create_dataset_and_wait(
    datasetName="l34_probe_eval_ds",
    schemaType="AGENTCORE_EVALUATION_PREDEFINED_V1",
    source={"inlineExamples": {"examples": examples}},
)
ds_id = ds["datasetId"]
print(f"create  -> status={ds['status']} id={ds_id} exampleCount={ds.get('exampleCount')}")

got = client.get_dataset(datasetId=ds_id)
print(f"get     -> status={got.get('status')} exampleCount={got.get('exampleCount')}")

ex = client.list_dataset_examples(datasetId=ds_id)
print(f"list    -> {len(ex.get('exampleSummaries', ex.get('examples', [])))} example summaries; keys={[k for k in ex if k!='ResponseMetadata']}")

ver = client.create_dataset_version_and_wait(datasetId=ds_id)
print(f"version -> datasetVersion={ver.get('datasetVersion')} status={ver.get('status')}")

client.delete_dataset_and_wait(datasetId=ds_id)
print("delete  -> ok (cleanup)")
print("LIFECYCLE OK")
