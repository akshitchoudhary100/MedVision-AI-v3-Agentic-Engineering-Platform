export type WorkflowStatus =
  | "idle"
  | "running"
  | "pending_review"
  | "approved"
  | "rejected"
  | "completed";

export type ToolStatus = "running" | "success" | "failed";
export type GateDecision = "approve" | "reject";

/** 1 Trigger, 2 Investigation, 3 Human gate, 4 Output */
export type LoopStep = 1 | 2 | 3 | 4;

export interface ToolEvent {
  /** Same id means the same call. A later event with the same id replaces the earlier one. */
  id: string;
  tool_name: string;
  status: ToolStatus;
  /** ISO 8601 */
  timestamp: string;
  input_params: Record<string, unknown>;
  output_data?: unknown;
}

export interface Evidence {
  logs: string[];
  metrics: Record<string, number>;
  /** Unified diff text. Empty string when there is no diff to show. */
  git_diff: string;
}

export interface WorkflowRun {
  id: string;
  query: string;
  status: WorkflowStatus;
  current_step: LoopStep;
  tool_events: ToolEvent[];
  evidence: Evidence;
  summary: string;
}

/** Payload of the SSE `status` event. Every field is optional so the backend can send partial updates. */
export interface RunUpdate {
  status?: WorkflowStatus;
  current_step?: LoopStep;
  summary?: string;
  evidence?: Evidence;
}

export interface RunStreamHandlers {
  onUpdate?: (update: RunUpdate) => void;
  onError?: (message: string) => void;
}

export const EMPTY_EVIDENCE: Evidence = { logs: [], metrics: {}, git_diff: "" };

export function stepForStatus(status: WorkflowStatus): LoopStep {
  switch (status) {
    case "idle":
      return 1;
    case "running":
      return 2;
    case "pending_review":
    case "rejected":
      return 3;
    case "approved":
    case "completed":
      return 4;
  }
}
