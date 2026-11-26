"""Capture actual AgentCore harness responses for human review.

Requires boto3, AWS credentials and SAFE_DESK_HARNESS_ARN. This script never
modifies infrastructure; each case gets a separate runtime session.
"""

import json
import os
import pathlib
import uuid
from datetime import datetime, timezone

import boto3


HERE = pathlib.Path(__file__).resolve().parent
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
ARN = os.environ.get("SAFE_DESK_HARNESS_ARN")
if not ARN:
    raise SystemExit("Set SAFE_DESK_HARNESS_ARN to the deployed harness ARN first.")

region = ARN.split(":")[3]
client = boto3.client("bedrock-agentcore", region_name=region)
report = {
    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    "harness_arn": ARN,
    "model": "global.amazon.nova-2-lite-v1:0",
    "review_note": "Responses are ungraded until a human checks them against expected behavior.",
    "results": [],
}

for case in CASES:
    session_id = str(uuid.uuid4())
    record = {"id": case["id"], "kind": case["kind"], "ticket": case["ticket"],
              "expected": case["expected"], "observed": "", "review": "PENDING"}
    try:
        response = client.invoke_harness(
            harnessArn=ARN,
            runtimeSessionId=session_id,
            messages=[{"role": "user", "content": [{"text": case["ticket"]}]}],
        )
        chunks = []
        for event in response["stream"]:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "text" in delta:
                    chunks.append(delta["text"])
            elif "runtimeClientError" in event:
                record["error"] = event["runtimeClientError"].get("message", "Unknown runtime error")
        record["observed"] = "".join(chunks)
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    report["results"].append(record)
    print(f"{case['id']}: {'error' if 'error' in record else 'captured'}")

path = HERE / "live-results.json"
path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Review responses in {path}")
