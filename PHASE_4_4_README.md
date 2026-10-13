# Phase 4.4 — FastAPI control-plane integration

## What changes

- Replaces the hard-coded/simulated investigation loop in `app/main.py` with calls to `app.workflows.persistent_investigation`.
- Uses the API-generated `run_id` as the LangGraph/PostgreSQL checkpoint `thread_id`.
- Runs the synchronous checkpointer + LLM graph in the executor instead of blocking FastAPI's event loop.
- Resumes real human review via `resume_persistent_review(run_id=..., decision=..., feedback=...)`.
- Preserves the existing route paths, including both root and `/api` prefixes, and preserves SSE event names (`status`, `tool_event`, `evidence`).
- Keeps a small in-process store for SSE queues/API presentation only. It is not durable workflow state; PostgreSQL checkpoints are the durable graph state.

## Configuration

Set the repository root the investigator should inspect. By default, the process current working directory is used:

```bash
export MEDVISION_V3_REPO_PATH="/absolute/path/to/MedVision-AI-v3-Agentic-Engineering-Platform"
```

Set the Postgres URL using the URL-encoded password if it includes special characters:

```bash
export LANGGRAPH_DATABASE_URL='postgresql://medvision:your_encoded_password@localhost:5432/medvision_v3'
```

Install the Phase 4.3 PostgreSQL dependencies in the same virtual environment used by Uvicorn. Make sure Ollama is running and `granite4:3b` is available, as specified by `langgraph_investigation_workflow.py`.

Start from the repository root:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Do not start with `uvicorn main:app` when the file is under `app/` unless you are intentionally running from the `app` directory.

## Important phase boundary / known limitation

This phase wires the existing API to the Phase 4 graph. The provided Phase 4.2 loop records successful tool *names*, not complete structured tool arguments/results. Therefore `tool_event` payloads currently indicate the successful tool name and avoid fabricating arguments or outputs. A future observability phase should add structured tool-call/result records directly to graph state. Likewise, the API projection and SSE queues are currently in-process, so the API cannot recover a run's UI event history after an API process restart even though LangGraph checkpoints are persisted in PostgreSQL. Durable run registry/event replay is a separate persistence concern.

The current investigation graph's final successful investigation state is expected to enter `human_review` and return a LangGraph interrupt. The API recognizes the interrupt payload and exposes `pending_review`; the gate endpoint resumes with the same `run_id`.

## Verify locally

1. Review the diff before replacing `app/main.py`.
2. Run syntax/import checks from the project root:

   ```bash
   python -m py_compile app/main.py
   python -m pytest -q
   ```

3. Start dependencies (PostgreSQL and Ollama), then start FastAPI.
4. Check `GET http://localhost:8000/api`.
5. Submit an investigation to `POST http://localhost:8000/api/workflows` with `{"query":"Inspect the repository architecture and summarize evidence from source files"}`.
6. Connect to `GET /api/workflows/{run_id}/events`. The workflow should emit `running`, then `evidence`, then `pending_review` if investigation succeeds.
7. Submit `POST /api/workflows/{run_id}/gate` with `{"decision":"approve"}` to resume it; or with `{"decision":"reject","feedback":"Please investigate the evidence gap in ..."}` to trigger revision.
8. Verify the checkpointer is usable across a new connection by resuming the same run and checking logs/DB state.

Do not claim Phase 4.4's real integration passed based only on syntax/API schema checks. The live LLM + PostgreSQL + interrupt/resume path still needs to be exercised on the project machine.
