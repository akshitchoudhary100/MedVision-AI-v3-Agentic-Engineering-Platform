import os
import uuid

from app.workflows.persistent_investigation import (
    invoke_persistent_investigation,
)

run_id = str(uuid.uuid4())

repo_path = os.environ["MEDVISION_V3_REPO_PATH"]

query = """
Investigate how Redis caching is implemented in this repository.

Determine:

1. Where Redis caching is implemented.
2. How the cache key is generated.
3. What TTL configuration is used.
4. How cache invalidation is handled.
5. Where Redis caching is integrated into the inference path.
6. How cache hits and cache misses affect inference execution.

Use actual source-code evidence.

Do not assume or invent implementation details.

Before considering the investigation complete, make sure the relevant
implementation and its integration into the inference path are supported
by inspected source files.

When choosing each tool, provide concise structured investigation metadata:
- action_reason: why this tool is needed now
- expected_information: what this tool should reveal
- completion_criteria: what evidence would indicate the investigation is complete
- missing_evidence: what important evidence is still missing

Do not provide private chain-of-thought. Only provide concise engineering
justification for the selected action.
""".strip()

print("=" * 70)
print("V2 REDIS INVESTIGATION — DIAGNOSTIC RUN")
print("=" * 70)
print("RUN ID:", run_id)
print("TARGET REPO:", repo_path)
print()
print("QUERY:")
print(query)
print("=" * 70)

result = invoke_persistent_investigation(
    run_id=run_id,
    query=query,
    repo_path=repo_path,
)

print("\n=== STATUS ===")
print(result.get("status"))

print("\n=== ATTEMPT ===")
print(result.get("attempt"))

print("\n=== ERRORS ===")
for error in result.get("errors", []):
    print(error)

print("\n=== SUMMARY ===")
print(result.get("summary", ""))

print("\n=== EVIDENCE ===")
for item in result.get("evidence", []):
    print(item)

print("\n=== TOOL CALLS ===")
print(result.get("tool_calls", []))

print("\n=== RESULT ===")
print(result.get("result", {}))

print("\n=== INTERRUPTED ===")
print(bool(result.get("__interrupt__")))

print("\n=== FULL RESULT ===")
print(result)
