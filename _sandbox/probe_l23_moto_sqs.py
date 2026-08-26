"""Probe: can moto back a real boto3 SQS client, including a DLQ RedrivePolicy?

Answers, before any rewrite of error_recovery.py Iterations 8/11:
  1. moto + boto3 versions actually installed
  2. does `mock_aws` cover sqs with the current extras, or is moto[sqs] needed
  3. does moto implement RedrivePolicy redrive (maxReceiveCount -> DLQ)
  4. does moto honour VisibilityTimeout on receive_message

Run: uv run python <this file>
"""

import json

import boto3
import moto
from moto import mock_aws  # nosim:ok moto serves the real SQS API in-process

print(f"moto  {moto.__version__}")
print(f"boto3 {boto3.__version__}")

REGION = "us-east-1"


@mock_aws  # nosim:ok moto serves the real SQS API in-process
def probe():
    sqs = boto3.client("sqs", region_name=REGION)

    dlq_url = sqs.create_queue(QueueName="probe-dlq")["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=dlq_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]
    print(f"dlq arn: {dlq_arn}")

    main_url = sqs.create_queue(
        QueueName="probe-main",
        Attributes={
            "VisibilityTimeout": "0",
            "RedrivePolicy": json.dumps(
                {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}
            ),
        },
    )["QueueUrl"]
    print(f"main url: {main_url}")

    sqs.send_message(QueueUrl=main_url, MessageBody=json.dumps({"order_id": 2}))

    # Receive the same message repeatedly; after maxReceiveCount it should redrive.
    for attempt in range(1, 6):
        resp = sqs.receive_message(
            QueueUrl=main_url,
            MaxNumberOfMessages=1,
            AttributeNames=["ApproximateReceiveCount"],
            VisibilityTimeout=0,
        )
        msgs = resp.get("Messages", [])
        if not msgs:
            print(f"  attempt {attempt}: main queue empty")
            continue
        count = msgs[0]["Attributes"]["ApproximateReceiveCount"]
        print(f"  attempt {attempt}: received, ApproximateReceiveCount={count}")

    dlq_msgs = sqs.receive_message(QueueUrl=dlq_url, MaxNumberOfMessages=10).get(
        "Messages", []
    )
    print(f"redrive worked: {len(dlq_msgs)} message(s) landed in the DLQ")

    # Visibility timeout behaviour
    vis_url = sqs.create_queue(
        QueueName="probe-vis", Attributes={"VisibilityTimeout": "30"}
    )["QueueUrl"]
    sqs.send_message(QueueUrl=vis_url, MessageBody="hello")
    first = sqs.receive_message(QueueUrl=vis_url).get("Messages", [])
    second = sqs.receive_message(QueueUrl=vis_url).get("Messages", [])
    print(f"visibility: first receive={len(first)}, immediate second={len(second)}")


probe()
print("probe complete")
