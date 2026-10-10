import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator


# ============================================================================
# Logging Configuration
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger("medvision-v3-backend")


# ============================================================================
# Pydantic Schemas & Data Models (Pydantic v2)
# ============================================================================

class WorkflowRequest(BaseModel):
    query: str = Field(
        ...,
        description="The investigation query submitted by the human engineer.",
        json_schema_extra={
            "example": "Why did async inference latency increase?"
        }
    )


class WorkflowResponse(BaseModel):
    run_id: str = Field(
        ...,
        description="Unique run identifier assigned to this workflow."
    )


class GateDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"] = Field(
        ...,
        description="Human gate review decision."
    )

    feedback: Optional[str] = Field(
        None,
        description="Feedback notes from reviewer. Mandatory on rejection."
    )

    @model_validator(mode="after")
    def validate_rejection_feedback(self) -> "GateDecisionRequest":
        if self.decision == "reject" and not (
            self.feedback and self.feedback.strip()
        ):
            raise ValueError(
                "Feedback string is required when submitting a 'reject' gate decision."
            )

        return self


class ToolEvent(BaseModel):
    id: str = Field(
        ...,
        description="Unique tool call execution ID."
    )

    tool_name: str = Field(
        ...,
        description="Name of the invoked diagnostic tool."
    )

    input_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input arguments."
    )

    output_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Execution result payload."
    )

    status: Literal["running", "success", "failed"] = Field(
        ...,
        description="Tool execution state."
    )

    timestamp: str = Field(
        ...,
        description="ISO timestamp."
    )


class StatusEvent(BaseModel):
    status: Literal[
        "running",
        "pending_review",
        "approved",
        "rejected",
        "completed"
    ] = Field(...)

    current_step: Optional[int] = Field(
        None,
        ge=1,
        le=4,
        description="Step index (1-4)."
    )

    summary: Optional[str] = Field(
        None,
        description="State transition description."
    )


class Evidence(BaseModel):
    logs: List[str] = Field(
        default_factory=list,
        description="Extracted log messages."
    )

    metrics: Dict[str, Union[float, int]] = Field(
        default_factory=dict,
        description="Numerical metric values."
    )

    git_diff: str = Field(
        "",
        description="Git unified diff output."
    )

    summary: Optional[str] = Field(
        None,
        description="High-level findings summary."
    )


# ============================================================================
# Global Thread-Safe In-Memory State Store
# ============================================================================

class WorkflowStateStore:

    def __init__(self):
        self.runs: Dict[str, Dict[str, Any]] = {}

        self.event_queues: Dict[
            str,
            asyncio.Queue
        ] = {}

        self.gate_events: Dict[
            str,
            asyncio.Event
        ] = {}

        self.gate_decisions: Dict[
            str,
            Dict[str, Any]
        ] = {}


state_store = WorkflowStateStore()


# ============================================================================
# Simulated Agent Runtime Engine
# ============================================================================

def get_iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_event(
    run_id: str,
    event_type: str,
    payload: Dict[str, Any]
):
    """
    Pushes a typed event onto the run's SSE queue.
    """

    if run_id in state_store.event_queues:
        await state_store.event_queues[run_id].put(
            (event_type, payload)
        )


async def run_investigation_loop(
    run_id: str,
    query: str
):
    """
    Asynchronous background engine simulating:

    - multi-step agent tool execution
    - evidence compilation
    - iterative human gate approval
    - workflow completion
    """

    logger.info(
        f"Starting investigation loop for run "
        f"{run_id} with query: '{query}'"
    )

    # ------------------------------------------------------------------------
    # Step 1: Trigger
    # ------------------------------------------------------------------------

    await emit_event(
        run_id,
        "status",
        StatusEvent(
            status="running",
            current_step=1,
            summary=(
                "Workflow triggered. "
                "Initializing agent runtime context..."
            )
        ).model_dump()
    )

    await asyncio.sleep(0.8)

    # ------------------------------------------------------------------------
    # Step 2: Investigation
    # ------------------------------------------------------------------------

    await emit_event(
        run_id,
        "status",
        StatusEvent(
            status="running",
            current_step=2,
            summary="Executing agent diagnostic tool loop..."
        ).model_dump()
    )

    # ------------------------------------------------------------------------
    # Tool Call 1: check_git_history
    # ------------------------------------------------------------------------

    tool1_id = "call_git_001"

    await emit_event(
        run_id,
        "tool_event",
        ToolEvent(
            id=tool1_id,
            tool_name="check_git_history",
            input_params={
                "path": "app/",
                "max_commits": 10
            },
            status="running",
            timestamp=get_iso_timestamp()
        ).model_dump()
    )

    await asyncio.sleep(1.2)

    await emit_event(
        run_id,
        "tool_event",
        ToolEvent(
            id=tool1_id,
            tool_name="check_git_history",
            input_params={
                "path": "app/",
                "max_commits": 10
            },
            output_data={
                "recent_commits": [
                    {
                        "commit": "a41c9e2",
                        "author": "dev",
                        "message": "chore: adjust default cache TTL"
                    },
                    {
                        "commit": "f82b10c",
                        "author": "lead",
                        "message": "feat: update async inference queue"
                    }
                ]
            },
            status="success",
            timestamp=get_iso_timestamp()
        ).model_dump()
    )

    # ------------------------------------------------------------------------
    # Tool Call 2: read_prometheus_metrics
    # ------------------------------------------------------------------------

    tool2_id = "call_prom_002"

    await emit_event(
        run_id,
        "tool_event",
        ToolEvent(
            id=tool2_id,
            tool_name="read_prometheus_metrics",
            input_params={
                "metric": "inference_latency_seconds",
                "quantile": 0.95,
                "window": "1h"
            },
            status="running",
            timestamp=get_iso_timestamp()
        ).model_dump()
    )

    await asyncio.sleep(1.4)

    await emit_event(
        run_id,
        "tool_event",
        ToolEvent(
            id=tool2_id,
            tool_name="read_prometheus_metrics",
            input_params={
                "metric": "inference_latency_seconds",
                "quantile": 0.95,
                "window": "1h"
            },
            output_data={
                "p95_latency_ms": 4100,
                "p95_latency_ms_24h_ago": 2650,
                "queue_depth": 14,
                "active_workers": 2
            },
            status="success",
            timestamp=get_iso_timestamp()
        ).model_dump()
    )

    # ------------------------------------------------------------------------
    # Tool Call 3: inspect_redis_cache
    # ------------------------------------------------------------------------

    tool3_id = "call_redis_003"

    await emit_event(
        run_id,
        "tool_event",
        ToolEvent(
            id=tool3_id,
            tool_name="inspect_redis_cache",
            input_params={
                "pattern": "pred:*",
                "stats": [
                    "hit_ratio",
                    "ttl_seconds"
                ]
            },
            status="running",
            timestamp=get_iso_timestamp()
        ).model_dump()
    )

    await asyncio.sleep(1.0)

    await emit_event(
        run_id,
        "tool_event",
        ToolEvent(
            id=tool3_id,
            tool_name="inspect_redis_cache",
            input_params={
                "pattern": "pred:*",
                "stats": [
                    "hit_ratio",
                    "ttl_seconds"
                ]
            },
            output_data={
                "cache_hit_ratio_pct": 12,
                "cache_hit_ratio_pct_24h_ago": 71,
                "current_ttl_seconds": 60
            },
            status="success",
            timestamp=get_iso_timestamp()
        ).model_dump()
    )

    # ------------------------------------------------------------------------
    # Compile Evidence
    # ------------------------------------------------------------------------

    findings_summary = (
        "Latency rose because the cache hit ratio fell from 71% to 12%. "
        "Commit a41c9e2 cut CACHE_TTL_SECONDS from 3600 to 60, so most requests now "
        "run full inference and the RQ queue backs up behind them.\n"
        "Suggested fix: restore the 3600 s TTL, or set TTLs per model."
    )

    evidence_payload = Evidence(
        logs=[
            "2026-10-09T10:45:12Z [INFO] app.inference: "
            "Request cache miss for key pred:img_90812",

            "2026-10-09T10:45:13Z [WARNING] app.rq_worker: "
            "Task queue depth exceeded threshold (depth=14)",

            "2026-10-09T10:45:15Z [INFO] app.redis: "
            "Key pred:img_90812 expired after 60s"
        ],

        metrics={
            "p95_latency_ms": 4100,
            "p95_latency_ms_24h_ago": 2650,
            "queue_depth": 14,
            "cache_hit_ratio_pct": 12,
            "cache_hit_ratio_pct_24h_ago": 71,
            "workers": 2
        },

        git_diff=(
            "diff --git a/app/config.py b/app/config.py\n"
            "index 83a1f92..b29e101 100644\n"
            "--- a/app/config.py\n"
            "+++ b/app/config.py\n"
            "@@ -14,3 +14,3 @@ class Settings:\n"
            "-    CACHE_TTL_SECONDS: int = 3600\n"
            "+    CACHE_TTL_SECONDS: int = 60\n"
        ),

        summary=findings_summary
    )

    # ------------------------------------------------------------------------
    # Emit Evidence Artifact
    # ------------------------------------------------------------------------

    await emit_event(
        run_id,
        "evidence",
        evidence_payload.model_dump()
    )

    # ------------------------------------------------------------------------
    # Human Review Gate
    # ------------------------------------------------------------------------

    while True:

        # Transition to Step 3
        state_store.runs[run_id]["status"] = "pending_review"

        await emit_event(
            run_id,
            "status",
            StatusEvent(
                status="pending_review",
                current_step=3,
                summary=(
                    "Investigation complete. "
                    "Awaiting human review approval..."
                )
            ).model_dump()
        )

        logger.info(
            f"Run {run_id} is now pausing at Human Review Gate..."
        )

        # Wait until human submits approve/reject
        gate_event = state_store.gate_events[run_id]

        await gate_event.wait()

        # Retrieve reviewer decision
        decision_data = state_store.gate_decisions.get(
            run_id,
            {}
        )

        decision = decision_data.get("decision")
        feedback = decision_data.get("feedback", "")

        # --------------------------------------------------------------------
        # Approval
        # --------------------------------------------------------------------

        if decision == "approve":

            logger.info(
                f"Run {run_id} APPROVED by human reviewer."
            )

            state_store.runs[run_id]["status"] = "approved"

            break

        # --------------------------------------------------------------------
        # Rejection
        # --------------------------------------------------------------------

        elif decision == "reject":

            logger.info(
                f"Run {run_id} REJECTED by human reviewer. "
                f"Feedback: '{feedback}'"
            )

            state_store.runs[run_id]["status"] = "rejected"

            await emit_event(
                run_id,
                "status",
                StatusEvent(
                    status="rejected",
                    current_step=3,
                    summary=(
                        f"Decision REJECTED. "
                        f"Incorporating feedback: {feedback}"
                    )
                ).model_dump()
            )

            # Reset event for secondary review
            gate_event.clear()

            # Simulate secondary remediation investigation
            await asyncio.sleep(1.5)

            tool4_id = (
                f"call_reinvestigate_"
                f"{uuid.uuid4().hex[:6]}"
            )

            await emit_event(
                run_id,
                "tool_event",
                ToolEvent(
                    id=tool4_id,
                    tool_name="reevaluate_remediation_plan",
                    input_params={
                        "reviewer_feedback": feedback
                    },
                    output_data={
                        "status": "adjusted",
                        "note": (
                            "Remediation plan updated "
                            "with reviewer feedback."
                        )
                    },
                    status="success",
                    timestamp=get_iso_timestamp()
                ).model_dump()
            )

            # Loop returns to pending_review


    # ------------------------------------------------------------------------
    # Step 4: Output / Hand-off
    # ------------------------------------------------------------------------

    await emit_event(
        run_id,
        "status",
        StatusEvent(
            status="approved",
            current_step=4,
            summary=(
                "Human gate passed. "
                "Preparing final engineering hand-off and diff output."
            )
        ).model_dump()
    )

    await asyncio.sleep(1.0)

    state_store.runs[run_id]["status"] = "completed"

    await emit_event(
        run_id,
        "status",
        StatusEvent(
            status="completed",
            current_step=4,
            summary="Workflow execution completed successfully."
        ).model_dump()
    )

    logger.info(
        f"Run {run_id} workflow loop finished successfully."
    )


# ============================================================================
# FastAPI Application Initialization & Middleware Setup
# ============================================================================

app = FastAPI(
    title="MedVision AI V3 Control Plane API",
    description=(
        "Backend human-in-the-loop control plane API "
        "for agentic engineering workflows."
    ),
    version="3.0.0"
)


# ============================================================================
# CORS
# ============================================================================

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Start Workflow Endpoint
# ============================================================================

@app.post(
    "/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_200_OK
)
@app.post(
    "/api/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_200_OK
)
async def start_workflow(req: WorkflowRequest):
    """
    Starts a new agent investigation run.
    """

    run_id = str(uuid.uuid4())

    # Initialize workflow state
    state_store.runs[run_id] = {
        "run_id": run_id,
        "query": req.query,
        "status": "running",
        "created_at": get_iso_timestamp()
    }

    # Create event queue
    state_store.event_queues[run_id] = asyncio.Queue()

    # Create human gate event
    state_store.gate_events[run_id] = asyncio.Event()

    # Start background investigation
    asyncio.create_task(
        run_investigation_loop(
            run_id,
            req.query
        )
    )

    logger.info(
        f"Initiated workflow run_id={run_id}"
    )

    return WorkflowResponse(
        run_id=run_id
    )


# ============================================================================
# SSE Event Stream
# ============================================================================

@app.get(
    "/workflows/{run_id}/events"
)
@app.get(
    "/api/workflows/{run_id}/events"
)
async def stream_workflow_events(
    run_id: str,
    request: Request
):
    """
    Establishes an SSE stream transmitting:

    - tool calls
    - status changes
    - evidence artifacts
    """

    if run_id not in state_store.runs:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{run_id}' not found."
        )

    async def event_generator():

        queue = state_store.event_queues[run_id]

        while True:

            # Check if browser disconnected
            if await request.is_disconnected():

                logger.info(
                    f"Client disconnected from SSE stream "
                    f"for run {run_id}"
                )

                break

            try:

                event_type, payload = await asyncio.wait_for(
                    queue.get(),
                    timeout=1.0
                )

                queue.task_done()

                data_json = json.dumps(payload)

                yield (
                    f"event: {event_type}\n"
                    f"data: {data_json}\n\n"
                )

                # Close stream after workflow completion
                if (
                    event_type == "status"
                    and payload.get("status") == "completed"
                ):
                    logger.info(
                        f"Workflow {run_id} completed. "
                        f"Closing SSE stream."
                    )

                    break

            except asyncio.TimeoutError:
                continue

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ============================================================================
# Human Gate Endpoint
# ============================================================================

@app.post(
    "/workflows/{run_id}/gate",
    response_model=StatusEvent,
    status_code=status.HTTP_200_OK
)
@app.post(
    "/api/workflows/{run_id}/gate",
    response_model=StatusEvent,
    status_code=status.HTTP_200_OK
)
async def submit_gate_decision(
    run_id: str,
    req: GateDecisionRequest
):
    """
    Receives human approval or rejection decision.
    """

    # Check workflow exists
    if run_id not in state_store.runs:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{run_id}' not found."
        )

    # Check workflow is actually waiting for review
    current_status = state_store.runs[run_id].get(
        "status"
    )

    if current_status != "pending_review":

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Workflow run '{run_id}' is not currently "
                f"awaiting review "
                f"(status: '{current_status}')."
            )
        )

    # Defense-in-depth validation
    if req.decision == "reject" and not (
        req.feedback and req.feedback.strip()
    ):

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Feedback string is required when "
                "submitting a 'reject' gate decision."
            )
        )

    # Save decision
    state_store.gate_decisions[run_id] = {
        "decision": req.decision,
        "feedback": req.feedback
    }

    # Wake up the waiting agent
    state_store.gate_events[run_id].set()

    new_status = (
        "approved"
        if req.decision == "approve"
        else "rejected"
    )

    return StatusEvent(
        status=new_status,
        current_step=3,
        summary=(
            f"Gate decision '{req.decision}' "
            f"recorded successfully."
        )
    )


# ============================================================================
# Health Check
# ============================================================================

@app.get("/")
@app.get("/api")
async def health_check():

    return {
        "status": "online",
        "platform": "MedVision AI V3 Control Plane API",
        "timestamp": get_iso_timestamp()
    }


# ============================================================================
# Uvicorn Execution Entrypoint
# ============================================================================

if __name__ == "__main__":

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )