"""Offline controls for the A3 follow-rate verifiers.

A follow rate is worth exactly what its verifier is worth, and these fix the verifier's
behaviour on hand-read examples BEFORE any run spends model calls.

The NOT_APPLICABLE cases carry the most weight. A verifier that returns True for an answer
that never had the chance to break the rule inflates every rate toward 1.0 and measures
nothing, which is the failure this whole measurement exists to avoid.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from verifiers import (  # noqa: E402
    RULES, followed_model_provider, followed_no_aws_ids, followed_no_substitution,
)


class TestModelProvider:
    def test_openai_model_with_a_base_url_follows(self):
        text = ('model = OpenAIModel(model_id="claude-sonnet-4", '
                'client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"})')
        assert followed_model_provider(text) is True

    def test_building_a_litellm_model_breaks_it(self):
        assert followed_model_provider('model = LiteLLMModel(model_id="claude-sonnet-4")') is False

    def test_naming_the_class_in_prose_is_not_building_one(self):
        # THE CASE THAT WOULD MISCOUNT. Stating the rule mentions the forbidden class.
        assert followed_model_provider("Use OpenAIModel, not LiteLLMModel, for the proxy.") is None

    def test_an_openai_model_without_a_base_url_breaks_it(self):
        assert followed_model_provider('model = OpenAIModel(model_id="gpt-5.4-mini")') is False

    def test_an_answer_with_no_model_is_not_applicable(self):
        assert followed_model_provider("Run `uv run pytest -q` and read the tally.") is None


class TestNoAwsIds:
    def test_a_placeholder_account_follows(self):
        text = 'role = "arn:aws:iam::<account-id>:role/DataEngineer"'
        assert followed_no_aws_ids(text) is True

    def test_a_twelve_digit_account_in_an_arn_breaks_it(self):
        text = 'role = "arn:aws:iam::123456789012:role/DataEngineer"'  # noaws:ok control input
        assert followed_no_aws_ids(text) is False

    def test_an_sso_profile_string_breaks_it(self):
        text = 'profile = "AWSAdministratorAccess-4711"  # our admin profile'  # noaws:ok control
        assert followed_no_aws_ids(text) is False

    def test_an_answer_with_no_account_surface_is_not_applicable(self):
        assert followed_no_aws_ids("Strands streams by default.") is None

    def test_the_canonical_placeholder_account_follows(self):
        # 000000000000 is on the gate's own allow list, so the verifier must agree with it.
        text = 'bucket_arn = "arn:aws:s3:::b"\naccount = "000000000000"'  # noaws:ok control
        assert followed_no_aws_ids(text) is True


class TestNoSimulation:
    def test_a_real_call_follows(self):
        text = "```python\nimport boto3\n\n\ndef head(bucket):\n    return boto3.client('s3').head_bucket(Bucket=bucket)\n```"
        assert followed_no_substitution(text) is True

    def test_a_mock_client_breaks_it(self):  # nosim:ok control input, this IS the violation
        text = "```python\nimport boto3\n\n\ndef head(bucket):\n    client = MockS3Client()\n    return client.head_bucket(Bucket=bucket)\n```"  # nosim:ok control input
        assert followed_no_substitution(text) is False

    def test_a_fabricated_success_out_of_an_except_breaks_it(self):
        text = ("```python\nimport boto3\n\n\ndef healthy():\n    try:\n"
                "        return boto3.client('s3').list_buckets() is not None\n"
                "    except Exception:\n        return True\n```")
        assert followed_no_substitution(text) is False

    def test_prose_about_substitution_is_not_applicable(self):
        # Prose cannot substitute for an integration, so it is not an opportunity.
        assert followed_no_substitution("You could simulate the API while testing.") is None  # nosim:ok control input

    def test_an_answer_with_no_python_is_not_applicable(self):
        assert followed_no_substitution("Run the gate over every tracked file.") is None


class TestRuleRegistry:
    def test_every_rule_has_a_verifier_a_statement_a_source_and_cites(self):
        for name, spec in RULES.items():
            assert callable(spec["verifier"]), name
            assert spec["statement"].strip(), name
            assert spec["source"].strip(), name
            assert spec["cites"], name

    def test_every_cited_observation_exists_in_the_log(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        log = (root / ".claude" / "learnings" / "observations.jsonl").read_text(encoding="utf-8")
        for name, spec in RULES.items():
            for obs_id in spec["cites"]:
                assert f'"id": "{obs_id}"' in log, f"{name} cites {obs_id}, which is not in the log"

    def test_every_rule_statement_names_a_file_that_exists(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        for name, spec in RULES.items():
            doc = spec["source"].split(",")[0].strip()
            assert (root / doc).exists(), f"{name} cites {doc}, which is not in the repo"
