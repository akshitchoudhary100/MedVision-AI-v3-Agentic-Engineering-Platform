# Phase 4.3 — PostgreSQL-backed LangGraph checkpoints

## Goal

Replace process-local checkpoint storage for the LangGraph investigation workflow
with PostgreSQL-backed checkpoint storage. This phase persists **LangGraph
execution state** so an interrupted graph can be resumed with the same
`thread_id`. It does not yet add application-domain tables for runs, findings,
tool calls, or audit history; those should be designed separately.

## Patch contents

- `app/orchestrator/postgres_checkpointer.py` — connection-scoped PostgresSaver factory.
- `app/workflows/persistent_investigation.py` — persistent start/resume entry points.
- `tests/test_postgres_checkpointer.py` — fast unit tests for configuration.
- `requirements-phase-4-3.txt` — dependency additions.

The existing `app/orchestrator/langgraph_graph.py` and `langgraph_state.py` are
not replaced by this patch. The adapter expects Phase 4.2's
`build_investigation_graph(checkpointer=..., investigator=...)` and
`resume_review(decision, feedback)` APIs.

## 1. Create a branch

Run inside the repository:

```bash
git status
git branch --show-current
git checkout -b phase-4-3-persistence
```

Only create the branch if you are currently on `phase-4-2-langgraph-agent-loop`
and have a clean working tree. If you already created it, do not create it again.

## 2. Apply the patch

Extract the ZIP into the repository root, preserving folders. It should merge
the included `app/` and `tests/` directories into the existing ones.

Do not delete or replace Phase 3 agent/tool/policy files in this phase.

## 3. Install dependencies

```bash
python -m pip install -r requirements-phase-4-3.txt
```

If you prefer maintaining one project dependency file, add the listed packages
to your existing `requirements.txt` instead of installing the supplemental file.

## 4. Start PostgreSQL

Use a local PostgreSQL installation or Docker. Example Docker command:

```bash
docker run --name medvision-v3-postgres \
  -e POSTGRES_USER=medvision \
  -e POSTGRES_PASSWORD=change_this_local_password \
  -e POSTGRES_DB=medvision_v3 \
  -p 5432:5432 \
  -d postgres:16
```

If the container already exists, start it rather than creating a duplicate:

```bash
docker start medvision-v3-postgres
```

Set a connection string in your shell (replace the password with your own):

```bash
export LANGGRAPH_DATABASE_URL='postgresql://medvision:change_this_local_password@localhost:5432/medvision_v3'
```

For local development, you may put `LANGGRAPH_DATABASE_URL=...` in `.env`, but
only if your app loads `.env` before calling the adapter. Never commit real
credentials; keep `.env` in `.gitignore`.

## 5. Run tests

First run tests that do not require PostgreSQL:

```bash
python -m pytest tests/test_postgres_checkpointer.py tests/test_langgraph_agent_loop.py tests/test_langgraph_foundation.py -q
```

Expected result: all tests pass. The first three tests in this phase do not
connect to PostgreSQL.

Then verify that PostgreSQL is reachable:

```bash
docker ps
```

The patch intentionally does not start a live LLM or run a repository
investigation as part of unit tests.

## 6. Use the persistent workflow entry points

Start a run:

```python
from app.workflows.persistent_investigation import invoke_persistent_investigation

result = invoke_persistent_investigation(
    run_id="local-run-001",
    query="Investigate the repository architecture and cite source evidence",
    repo_path="/absolute/path/to/MedVision-AI-v3-Agentic-Engineering-Platform",
)
print(result)
```

When the graph reaches its human-review interrupt, record the `run_id`. Resume
the same workflow later:

```python
from app.workflows.persistent_investigation import resume_persistent_review

result = resume_persistent_review(
    run_id="local-run-001",
    decision="approve",  # use the decision strings accepted by your graph
)
print(result)
```

If rejecting, pass actionable feedback:

```python
result = resume_persistent_review(
    run_id="local-run-001",
    decision="reject",
    feedback="The findings need evidence from at least two distinct source files.",
)
```

**Important:** the decision names must match the Phase 4.2 graph's accepted
values. If that graph uses a different spelling (for example `approved` rather
than `approve`), use the exact accepted value. The adapter intentionally
delegates decision validation to the graph.

## 7. Verify persistence, then commit

Run the focused suite and the complete suite:

```bash
python -m pytest tests/test_postgres_checkpointer.py tests/test_langgraph_agent_loop.py tests/test_langgraph_foundation.py -q
python -m pytest -q
git status
git diff --check
```

If all tests pass:

```bash
git add app/orchestrator/postgres_checkpointer.py
git add app/workflows/persistent_investigation.py
git add tests/test_postgres_checkpointer.py
git add PHASE_4_3_README.md
git add requirements-phase-4-3.txt
git commit -m "feat: add PostgreSQL LangGraph checkpoint persistence"
```

## Scope and known limits

- This is a checkpoint persistence slice, not yet the full production persistence
  layer.
- `PostgresSaver.setup()` creates LangGraph's internal checkpoint tables.
- A durable resume requires the same `run_id`/`thread_id` and an interrupted
  checkpoint already written to PostgreSQL.
- `InMemorySaver` remains useful for fast unit tests.
- The adapter does not alter `app/main.py`, the FastAPI routes, or the frontend.
- Do not store secrets in graph state. Checkpoint state may contain prompts,
  evidence, and tool outputs, so protect the database and follow data-retention
  rules.
- If the Phase 4.2 graph has different exported function names or state fields,
  stop and reconcile those signatures before running the persistent adapter;
  do not paper over a mismatch by changing tests to pass.
