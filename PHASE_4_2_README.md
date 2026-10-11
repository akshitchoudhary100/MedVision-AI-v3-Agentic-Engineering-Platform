# MedVision AI V3 — Phase 4.2: LangGraph-controlled agent loop

## Goal

Phase 4.1 added the outer workflow and human-review interrupt, but wrapped the previous `ToolCallingAgent.run()` loop in one node. Phase 4.2 moves the per-step reasoning/tool loop under LangGraph control while keeping the existing `BaseLLM`/`OllamaLLM`, `ToolRegistry`, tool implementations, and `InvestigationPolicy`.

## Graph nodes

`initialize → reason → validate_tool → execute_tool → observe → reason`

The reasoning node either requests one tool call or proposes a final answer. The validation node applies policy, required-argument checks, duplicate-search prevention, discovered-file checks, repository path confinement and budgets. Only validated requests reach `execute_tool`. `observe` feeds tool output back into the conversation state. A final answer is accepted only after at least two distinct source files have been inspected. The outer Phase 4.1 graph still handles human review, approval and rejection/revision.

## What stays unchanged

- Ollama remains the LLM provider (`OllamaLLM(model="granite4:3b")` for the existing workflow).
- Existing search/read/git tools and registry are reused.
- The old `ToolCallingAgent` stays in the repo for compatibility/comparison, but the default Phase 4.1 workflow now calls `run_langgraph_investigation`, not `ToolCallingAgent.run()`.
- `app/main.py` and frontend/API routes are not touched in this phase. Their current simulated flow will still need a later integration phase.
- No V2 files are changed.

## Apply on your local repository

Start from your **local Phase 4.1 branch and its commit**. Do not base the branch on the public Phase 3 branch because that remote branch does not contain the Phase 4.1 files.

```bash
git status
git branch --show-current
# Expected branch: phase-4-1-langgraph-foundation
git checkout -b phase-4-2-langgraph-agent-loop
```

Then unzip the patch into a temporary directory. Copy the two included `app/orchestrator/` files and the new `app/workflows/langgraph_investigation_workflow.py` into their matching local directories; overwrite only `app/orchestrator/langgraph_graph.py`. Copy `tests/test_langgraph_agent_loop.py` into your existing tests directory. Keep your existing `requirements.txt` and verify it contains `langgraph>=1.0,<2`; do not replace it with a patch copy. Do not replace your whole `app/` or `tests/` directories. Preserve any unrelated local edits.

Ensure `requirements.txt` contains:

```text
langgraph>=1.0,<2
```

Install/check dependencies and run:

```bash
python -m pip install -r requirements.txt
python -m pytest tests/test_langgraph_agent_loop.py tests/test_langgraph_foundation.py -q
```

The new agent-loop tests use fake LLM/tool components and do not require Ollama. The foundation tests should also remain green.

## Security and limits

- The model cannot execute tools directly; tool requests pass through the policy and runtime validation node.
- File reads must be inside the selected repository and must reference files previously discovered by `search_code`.
- Search, source inspection, duplicate query and reasoning-step budgets are enforced by graph state.
- The graph still accepts a repo path from its caller. Before exposing it via the API, validate that path against an application-owned allow-list.

## Known scope boundary

Phase 4.2 does not alter `app/main.py`, its in-memory store/SSE API, or the frontend. The current FastAPI endpoints remain simulated until a later phase connects them to this graph. The inner agent-loop graph is currently compiled without a persistent checkpointer; durable PostgreSQL checkpointing remains Phase 4.3.
