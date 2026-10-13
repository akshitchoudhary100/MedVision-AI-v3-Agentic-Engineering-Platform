from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from concurrent.futures import Future
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Literal, Optional, Union

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

# ==========================================================================
# Logging
# ==========================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("medvision-v3-backend")

# ==========================================================================
# API DTOs: kept compatible with the existing Next.js control plane
# ==========================================================================


class WorkflowRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Investigation query submitted by the human engineer.",
        json_schema_extra={"example": "Investigate why async inference latency increased."},
    )

    @model_validator(mode="after")
    def validate_query(self) -> "WorkflowRequest":
        if not self.query.strip():
            raise ValueError("query must not be blank")
        return self


class WorkflowResponse(BaseModel):
    run_id: str = Field(..., description="Unique identifier and LangGraph thread_id.")


class GateDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    feedback: Optional[str] = None

    @model_validator(mode="after")
    def validate_rejection_feedback(self) -> "GateDecisionRequest":
        if self.decision == "reject" and not (self.feedback and self.feedback.strip()):
            raise ValueError("Feedback string is required when submitting a 'reject' gate decision.")
        return self


# Resolve forward annotations explicitly (also supports module-loader-based tests).
GateDecisionRequest.model_rebuild(_types_namespace={"Literal": Literal, "Optional": Optional})


class ToolEvent(BaseModel):
    id: str
    tool_name: str
    input_params: Dict[str, Any] = Field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    status: Literal["running", "success", "failed"]
    timestamp: str


class StatusEvent(BaseModel):
    status: Literal["running", "pending_review", "approved", "rejected", "completed"]
    current_step: Optional[int] = Field(None, ge=1, le=4)
    summary: Optional[str] = None


class Evidence(BaseModel):
    logs: List[str] = Field(default_factory=list)
    metrics: Dict[str, Union[float, int]] = Field(default_factory=dict)
    git_diff: str = ""
    summary: Optional[str] = None


# ==========================================================================
# In-process API projection and SSE broker
#
# LangGraph/PostgreSQL is the source of durable workflow state. This store only
# tracks API-facing summaries/event delivery for this web process. It is not a
# replacement for the checkpointer and is intentionally not presented as the
# canonical workflow state.
# ==========================================================================


def get_iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowStateStore:
    def __init__(self) -> None:
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.event_queues: Dict[str, asyncio.Queue] = {}
        self.tasks: Dict[str, Future] = {}
        self.lock = threading.RLock()

    def exists(self, run_id: str) -> bool:
        with self.lock:
            return run_id in self.runs

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            row = self.runs.get(run_id)
            return dict(row) if row is not None else None

    def patch(self, run_id: str, **values: Any) -> None:
        with self.lock:
            if run_id in self.runs:
                self.runs[run_id].update(values)


state_store = WorkflowStateStore()


async def emit_event(run_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    queue = state_store.event_queues.get(run_id)
    if queue is not None:
        await queue.put((event_type, payload))


def _publish_from_worker(run_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    """Bridge a worker thread into the event loop that owns the SSE queues."""
    loop = _event_loop
    if loop is None or loop.is_closed():
        logger.warning("Cannot publish %s for run %s: API event loop is unavailable", event_type, run_id)
        return
    try:
        asyncio.run_coroutine_threadsafe(emit_event(run_id, event_type, payload), loop).result(timeout=5)
    except Exception:
        logger.exception("Failed to publish %s event for run %s", event_type, run_id)


_event_loop: Optional[asyncio.AbstractEventLoop] = None


# ==========================================================================
# LangGraph integration helpers
# ==========================================================================


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _serialize_output(value: Any) -> Any:
    """Convert tool/evidence values to JSON-friendly output without inventing data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _serialize_output(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_output(v) for v in value]
    if hasattr(value, "model_dump"):
        return _serialize_output(value.model_dump(mode="json"))
    if hasattr(value, "as_text"):
        return str(value.as_text())
    return str(value)


def _status_payload(state: Dict[str, Any], *, summary: str, status_value: str | None = None) -> Dict[str, Any]:
    resolved_status = status_value or str(state.get("status", "running"))
    if resolved_status == "failed":
        # Preserve the frontend's existing status union. A failure is reported in
        # the summary and logs; 'rejected' is reserved for an exhausted/rejected review.
        resolved_status = "completed"
        summary = f"Workflow failed: {summary}"
    allowed = {"running", "pending_review", "approved", "rejected", "completed"}
    if resolved_status not in allowed:
        resolved_status = "running"
    return StatusEvent(
        status=resolved_status,
        current_step=(1 if resolved_status == "running" else 3 if resolved_status in {"pending_review", "rejected"} else 4),
        summary=summary,
    ).model_dump()


def _emit_status(run_id: str, state: Dict[str, Any], summary: str, status_value: str | None = None) -> None:
    payload = _status_payload(state, summary=summary, status_value=status_value)
    state_store.patch(run_id, status=payload["status"], updated_at=get_iso_timestamp(), state=_serialize_output(state))
    _publish_from_worker(run_id, "status", payload)


def _extract_interrupts(graph_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract LangGraph interrupt payloads when available across LangGraph versions."""
    interrupts = graph_result.get("__interrupt__", []) if isinstance(graph_result, dict) else []
    payloads: List[Dict[str, Any]] = []
    for item in interrupts or []:
        value = getattr(item, "value", item)
        if isinstance(value, dict):
            payloads.append(value)
    return payloads


def _evidence_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    result = state.get("result") if isinstance(state.get("result"), dict) else {}
    evidence = state.get("evidence") or result.get("evidence") or []
    findings = state.get("findings") or result.get("findings") or []
    summary = state.get("summary") or result.get("summary") or ""
    logs = [str(item) for item in evidence] if isinstance(evidence, list) else [str(evidence)]
    if findings:
        logs.extend(str(item) for item in findings)
    payload = Evidence(logs=logs, metrics={}, git_diff="", summary=str(summary)).model_dump()
    return payload


def _emit_tool_events(run_id: str, state: Dict[str, Any], previous_count: int) -> int:
    """Emit newly observed tool calls from LangGraph's checkpointed state."""
    calls = state.get("tool_calls", []) or []
    if not isinstance(calls, list):
        return previous_count
    # Phase 4.2 records successful tool names rather than structured invocation
    # payloads, so we report only data actually available instead of fabricating
    # input/output details.
    current_count = len(calls)
    for index, name in enumerate(calls[previous_count:current_count], start=previous_count):
        payload = ToolEvent(
            id=f"{run_id}-tool-{index + 1}",
            tool_name=str(name),
            input_params={},
            output_data={"note": "Tool completed; Phase 4.2 state currently records tool names only."},
            status="success",
            timestamp=get_iso_timestamp(),
        ).model_dump()
        _publish_from_worker(run_id, "tool_event", payload)
    return current_count


def _run_persistent_workflow(run_id: str, query: str, repo_path: str) -> None:
    """Start graph execution from a worker thread; checkpoints go to PostgreSQL."""
    try:
        _publish_from_worker(run_id, "status", StatusEvent(
            status="running", current_step=1, summary="Workflow accepted. Initializing persistent LangGraph runtime."
        ).model_dump())
        _publish_from_worker(run_id, "status", StatusEvent(
            status="running", current_step=2, summary="Running repository investigation through LangGraph and Ollama."
        ).model_dump())

        # Imported lazily so health checks and API schema loading do not require
        # an active PostgreSQL connection or an initialized local Ollama model.
        from app.workflows.persistent_investigation import invoke_persistent_investigation

        graph_result = invoke_persistent_investigation(
            run_id=run_id,
            query=query,
            repo_path=repo_path,
        )
        state = graph_result if isinstance(graph_result, dict) else {}
        state_store.patch(run_id, state=_serialize_output(state))
        count = _emit_tool_events(run_id, state, 0)
        run_status = str(state.get("status", "failed"))

        if run_status == "pending_review" or _extract_interrupts(state):
            state_store.patch(
                run_id,
                status="pending_review",
                review={
                    "summary": state.get("summary", ""),
                    "findings": state.get("findings", []),
                    "evidence": state.get("evidence", []),
                    "attempt": state.get("attempt", 1),
                },
                last_tool_count=count,
            )
            _publish_from_worker(run_id, "evidence", _evidence_payload(state))
            _emit_status(run_id, state, "Investigation complete. Awaiting human review.", "pending_review")
        elif run_status in {"approved", "completed"}:
            _publish_from_worker(run_id, "evidence", _evidence_payload(state))
            _emit_status(run_id, state, "Workflow completed successfully.", "completed")
        elif run_status == "rejected":
            _publish_from_worker(run_id, "evidence", _evidence_payload(state))
            _emit_status(run_id, state, "Review rejected; maximum revision attempts reached.", "rejected")
        else:
            errors = state.get("errors", [])
            reason = "; ".join(str(item) for item in errors) if errors else "Investigation did not complete successfully."
            state_store.patch(run_id, error=reason)
            _publish_from_worker(run_id, "evidence", _evidence_payload(state))
            _emit_status(run_id, state, reason, "completed")
    except Exception as exc:
        logger.exception("Workflow %s failed", run_id)
        message = f"Workflow execution failed: {exc}"
        state_store.patch(run_id, error=message)
        _publish_from_worker(run_id, "status", StatusEvent(
            status="completed", current_step=4, summary=message
        ).model_dump())


def _resume_persistent_workflow(run_id: str, decision: str, feedback: str) -> None:
    try:
        from app.workflows.persistent_investigation import resume_persistent_review

        _publish_from_worker(run_id, "status", StatusEvent(
            status="rejected" if decision == "reject" else "approved",
            current_step=3,
            summary=(f"Reviewer rejected the investigation: {feedback}" if decision == "reject" else "Human reviewer approved the investigation."),
        ).model_dump())

        state = resume_persistent_review(
            run_id=run_id,
            decision=decision,
            feedback=feedback,
        )
        state = state if isinstance(state, dict) else {}
        state_store.patch(run_id, state=_serialize_output(state))
        previous_count = int((state_store.get(run_id) or {}).get("last_tool_count", 0))
        new_count = _emit_tool_events(run_id, state, previous_count)
        state_store.patch(run_id, last_tool_count=new_count)
        state_status = str(state.get("status", "failed"))

        if state_status == "pending_review" or _extract_interrupts(state):
            state_store.patch(
                run_id,
                status="pending_review",
                review={
                    "summary": state.get("summary", ""),
                    "findings": state.get("findings", []),
                    "evidence": state.get("evidence", []),
                    "attempt": state.get("attempt", 1),
                },
            )
            _publish_from_worker(run_id, "evidence", _evidence_payload(state))
            _emit_status(run_id, state, "Revised investigation is ready for another human review.", "pending_review")
        elif state_status in {"completed", "approved"}:
            _publish_from_worker(run_id, "evidence", _evidence_payload(state))
            _emit_status(run_id, state, "Human review approved. Workflow completed.", "completed")
        elif state_status == "rejected":
            _publish_from_worker(run_id, "evidence", _evidence_payload(state))
            _emit_status(run_id, state, "Review rejected; maximum revision attempts reached.", "rejected")
        else:
            errors = state.get("errors", [])
            reason = "; ".join(str(item) for item in errors) if errors else "Workflow did not complete successfully."
            state_store.patch(run_id, error=reason)
            _emit_status(run_id, state, reason, "completed")
    except Exception as exc:
        logger.exception("Failed to resume review for workflow %s", run_id)
        message = f"Could not resume workflow: {exc}"
        state_store.patch(run_id, error=message)
        _publish_from_worker(run_id, "status", StatusEvent(
            status="completed", current_step=4, summary=message
        ).model_dump())


# ==========================================================================
# FastAPI app and middleware
# ==========================================================================

@asynccontextmanager
async def lifespan(_: FastAPI):
    global _event_loop
    _event_loop = asyncio.get_running_loop()
    try:
        yield
    finally:
        _event_loop = None


app = FastAPI(
    title="MedVision AI V3 Control Plane API",
    description="Human-in-the-loop control plane for persistent LangGraph engineering investigations.",
    version="4.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================================================
# Start workflow. The in-process executor is a transitional Phase 4.4 bridge;
# durable graph state lives in PostgreSQL via PostgresSaver.
# ==========================================================================

@app.post("/workflows", response_model=WorkflowResponse, status_code=status.HTTP_200_OK)
@app.post("/api/workflows", response_model=WorkflowResponse, status_code=status.HTTP_200_OK)
async def start_workflow(req: WorkflowRequest) -> WorkflowResponse:
    if not req.query.strip():
        raise HTTPException(status_code=422, detail="query must not be blank")

    # Keep the repository boundary explicit. A deployment can override this to
    # point at a sandbox/worktree root without changing the frontend contract.
    default_repo = os.getenv("MEDVISION_V3_REPO_PATH", os.getcwd())
    repo_path = os.path.realpath(os.path.expanduser(default_repo))
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=500, detail=f"Configured investigation repository does not exist: {repo_path}")

    run_id = str(uuid.uuid4())
    state_store.runs[run_id] = {
        "run_id": run_id,
        "query": req.query.strip(),
        "status": "running",
        "created_at": get_iso_timestamp(),
        "repo_path": repo_path,
    }
    state_store.event_queues[run_id] = asyncio.Queue()

    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(None, _run_persistent_workflow, run_id, req.query.strip(), repo_path)
    state_store.tasks[run_id] = task  # type: ignore[assignment]
    logger.info("Started persistent LangGraph run_id=%s repo=%s", run_id, repo_path)
    return WorkflowResponse(run_id=run_id)


# ==========================================================================
# SSE: existing event names and JSON payload shape preserved
# ==========================================================================

@app.get("/workflows/{run_id}/events")
@app.get("/api/workflows/{run_id}/events")
async def stream_workflow_events(run_id: str, request: Request) -> StreamingResponse:
    if not state_store.exists(run_id):
        raise HTTPException(status_code=404, detail=f"Workflow run '{run_id}' not found in this API process.")

    async def event_generator():
        queue = state_store.event_queues[run_id]
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected from workflow %s", run_id)
                break
            try:
                event_type, payload = await asyncio.wait_for(queue.get(), timeout=1.0)
                queue.task_done()
                yield f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
                if event_type == "status" and payload.get("status") == "completed":
                    break
                if event_type == "status" and payload.get("status") == "rejected":
                    # Rejection can be an intermediate review decision followed by
                    # another investigation. Close only when the API projection is terminal.
                    current = state_store.get(run_id) or {}
                    if current.get("status") == "rejected":
                        break
            except asyncio.TimeoutError:
                # Keep-alive comment prevents some proxies from treating a quiet
                # human-review pause as a dead connection.
                yield ": keep-alive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ==========================================================================
# Human gate: resume the PostgreSQL-backed graph using the same run_id/thread_id
# ==========================================================================

@app.post("/workflows/{run_id}/gate", response_model=StatusEvent, status_code=status.HTTP_200_OK)
@app.post("/api/workflows/{run_id}/gate", response_model=StatusEvent, status_code=status.HTTP_200_OK)
async def submit_gate_decision(run_id: str, req: GateDecisionRequest) -> StatusEvent:
    run = state_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Workflow run '{run_id}' not found in this API process.")
    if run.get("status") != "pending_review":
        raise HTTPException(
            status_code=400,
            detail=f"Workflow run '{run_id}' is not currently awaiting review (status: '{run.get('status')}').",
        )

    feedback = (req.feedback or "").strip()
    loop = asyncio.get_running_loop()
    state_store.patch(run_id, status="running", last_review_decision=req.decision)
    state_store.tasks[run_id] = loop.run_in_executor(None, _resume_persistent_workflow, run_id, req.decision, feedback)  # type: ignore[assignment]

    return StatusEvent(
        status="rejected" if req.decision == "reject" else "approved",
        current_step=3,
        summary=f"Gate decision '{req.decision}' accepted; resuming persistent LangGraph workflow.",
    )


# ==========================================================================
# Health check
# ==========================================================================

@app.get("/")
@app.get("/api")
async def health_check() -> Dict[str, str]:
    return {
        "status": "online",
        "platform": "MedVision AI V3 Control Plane API",
        "runtime": "LangGraph + PostgreSQL checkpoint persistence",
        "timestamp": get_iso_timestamp(),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
