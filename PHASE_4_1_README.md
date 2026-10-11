# MedVision AI V3 — Phase 4.1 LangGraph foundation

## Scope of this first vertical slice

- Adds a typed LangGraph state.
- Wraps the existing `app.workflows.investigation_workflow.run_investigation` entry point, preserving the current Ollama adapter, tool registry, policies, and repository investigation safeguards.
- Adds a persistent-checkpoint-compatible human-review interrupt.
- Approval finalizes the run; rejection with feedback invokes a revised investigation and returns to review.
- Adds graph tests with an injected fake investigator so tests do not require Ollama or access to a real repository.

**Important limitation:** this is the compatibility stage, not yet the final per-tool LangGraph migration. The current `ToolCallingAgent` still owns its internal LLM/tool loop. Phase 4.2 should extract that loop into graph nodes so LangGraph controls each model call, policy check, tool execution, observation, and routing decision.

## Apply

From the repository root on a new branch based on `phase-3-llm-tool-calling`:

```bash
git switch -c phase-4-1-langgraph-foundation
unzip /path/to/medvision_phase4_1_patch.zip -d /tmp/medvision-phase4
cp -R /tmp/medvision-phase4/app /path/to/MedVision-AI-v3-Agentic-Engineering-Platform/
cp -R /tmp/medvision-phase4/tests /path/to/MedVision-AI-v3-Agentic-Engineering-Platform/
cp /tmp/medvision-phase4/PHASE_4_1_README.md /path/to/MedVision-AI-v3-Agentic-Engineering-Platform/
```

Replace `/path/to/MedVision-AI-v3-Agentic-Engineering-Platform` with your local repo path. If applying manually, copy only the new files; do not overwrite existing `app` or `tests` directories wholesale.

Add this dependency to the existing `requirements.txt`:

```text
langgraph>=1.0,<2
```

Then run:

```bash
python -m pip install -r requirements.txt
python -m pytest tests/test_langgraph_foundation.py -q
```

If your installed LangGraph version does not expose `InMemorySaver` at `langgraph.checkpoint.memory`, check the installed version and align it with the package version in the requirements file.

## Checkpoint contract

Every invocation/resumption must use the same config:

```python
config = {"configurable": {"thread_id": run_id}}
```

The current test checkpointer is in-memory only. PostgreSQL checkpointer and application tables are intentionally Phase 4.3, not implied to be implemented here.

## Frontend/API compatibility

This patch does not change `app/main.py` or frontend files, so the existing API contract remains unchanged. Phase 4.1 tests the graph in isolation. Phase 4.4/4.5 will connect the graph to the existing FastAPI gate endpoint and SSE stream without changing the public route or event names.

## Safety boundary

- The existing `ToolCallingAgent` and policy remain responsible for current tool permissions.
- The graph does not accept an arbitrary tool registry or repository path from the model.
- The caller must validate `repo_path` against an application-owned allow-list before exposing this graph through FastAPI. Do not expose arbitrary filesystem paths directly to clients.
- V2 is not modified or imported as an application dependency.
