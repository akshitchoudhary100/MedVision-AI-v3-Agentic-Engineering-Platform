import type {
  Evidence,
  GateDecision,
  RunStreamHandlers,
  RunUpdate,
  ToolEvent,
} from "@/types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

/** Set NEXT_PUBLIC_USE_MOCK=true to skip the backend entirely and always play the simulated run. */
const FORCE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
const CONNECT_TIMEOUT_MS = 3000;

export interface StartedWorkflow {
  run_id: string;
  /** True when no backend was reachable and the run is simulated in the browser. */
  mock: boolean;
}

async function safeText(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return "";
  }
}

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

/**
 * POST /workflows {query} -> {run_id}
 *
 * If the backend can't be reached (network error or timeout), falls back to a
 * simulated run so the control plane works before the FastAPI side exists.
 * An HTTP error from a reachable backend is NOT masked: it throws.
 */
export async function startWorkflow(query: string): Promise<StartedWorkflow> {
  if (FORCE_MOCK) return startMock(query);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONNECT_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/workflows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal: controller.signal,
    });
  } catch {
    return startMock(query);
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    throw new Error(`The API rejected the request (${res.status}). ${await safeText(res)}`.trim());
  }

  const body = (await res.json()) as { run_id?: string };
  if (!body.run_id) throw new Error("The API response did not include a run_id.");
  return { run_id: body.run_id, mock: false };
}

/** POST /workflows/{id}/gate {decision, feedback} */
export async function submitGateDecision(
  runId: string,
  decision: GateDecision,
  feedback?: string,
): Promise<void> {
  if (mockRuns.has(runId)) {
    mockDecision(runId, decision, feedback ?? "");
    return;
  }

  const res = await fetch(`${API_BASE}/workflows/${encodeURIComponent(runId)}/gate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, feedback: feedback ?? "" }),
  });

  if (!res.ok) {
    throw new Error(`The API rejected your decision (${res.status}). ${await safeText(res)}`.trim());
  }
}

/**
 * GET /workflows/{id}/events (Server-Sent Events). Named events:
 *   tool_event  ToolEvent
 *   status      RunUpdate   (the backend should end the run with {status: "completed"})
 *   evidence    Evidence
 *
 * `onEvent` receives tool events. Status, evidence and errors go to `handlers`.
 * Returns a function that closes the stream.
 */
export function subscribeToRunEvents(
  runId: string,
  onEvent: (event: ToolEvent) => void,
  handlers: RunStreamHandlers = {},
): () => void {
  if (mockRuns.has(runId)) return subscribeMock(runId, onEvent, handlers);

  const source = new EventSource(`${API_BASE}/workflows/${encodeURIComponent(runId)}/events`);

  const listen = <T>(name: string, fn: (data: T) => void) => {
    source.addEventListener(name, (e) => {
      try {
        fn(JSON.parse((e as MessageEvent<string>).data) as T);
      } catch {
        handlers.onError?.(`The API sent a malformed "${name}" event.`);
      }
    });
  };

  listen<ToolEvent>("tool_event", onEvent);
  listen<RunUpdate>("status", (update) => {
    handlers.onUpdate?.(update);
    if (update.status === "completed") source.close();
  });
  listen<Evidence>("evidence", (evidence) => handlers.onUpdate?.({ evidence }));

  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) {
      handlers.onError?.("The event stream closed unexpectedly. Check that the API is running.");
    }
  };

  return () => source.close();
}

/* ------------------------------------------------------------------ */
/* Simulated backend (demo mode)                                       */
/* ------------------------------------------------------------------ */

interface MockRun {
  query: string;
  attempt: number;
  timers: ReturnType<typeof setTimeout>[];
  onEvent?: (event: ToolEvent) => void;
  handlers: RunStreamHandlers;
}

const mockRuns = new Map<string, MockRun>();

function startMock(query: string): StartedWorkflow {
  const id = `demo-${Math.random().toString(36).slice(2, 8)}`;
  mockRuns.set(id, { query, attempt: 0, timers: [], handlers: {} });
  return { run_id: id, mock: true };
}

function at(run: MockRun, ms: number, fn: () => void) {
  run.timers.push(setTimeout(fn, ms));
}

function clearTimers(run: MockRun) {
  run.timers.forEach(clearTimeout);
  run.timers = [];
}

function toolCall(
  run: MockRun,
  id: string,
  tool_name: string,
  input_params: Record<string, unknown>,
  output_data: unknown,
  startMs: number,
  durationMs: number,
) {
  at(run, startMs, () =>
    run.onEvent?.({ id, tool_name, status: "running", timestamp: new Date().toISOString(), input_params }),
  );
  at(run, startMs + durationMs, () =>
    run.onEvent?.({
      id,
      tool_name,
      status: "success",
      timestamp: new Date().toISOString(),
      input_params,
      output_data,
    }),
  );
}

const MOCK_DIFF = [
  "diff --git a/app/config.py b/app/config.py",
  "index 3f2a1c9..b81d4e0 100644",
  "--- a/app/config.py",
  "+++ b/app/config.py",
  "@@ -14,3 +14,3 @@",
  '     REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")',
  '     REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))',
  '-    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))',
  '+    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "60"))',
].join("\n");

function mockEvidence(): Evidence {
  const stamp = () => new Date().toLocaleTimeString("en-GB");
  return {
    logs: [
      `[${stamp()}] check_git_history: 3 commits touched app/ in the last 7 days`,
      `[${stamp()}] read_prometheus_metrics: p95 inference latency 4100 ms (2650 ms 24h ago)`,
      `[${stamp()}] inspect_redis_cache: hit ratio 12% (71% 24h ago), sampled key TTLs all under 60 s`,
      `[${stamp()}] correlation: the hit-ratio drop starts at the same time as commit a41c9e2`,
    ],
    metrics: {
      p95_latency_ms: 4100,
      p95_latency_ms_24h_ago: 2650,
      queue_depth: 14,
      cache_hit_ratio_pct: 12,
      cache_hit_ratio_pct_24h_ago: 71,
      workers: 2,
    },
    git_diff: MOCK_DIFF,
  };
}

function playInvestigation(run: MockRun, reviewerFeedback?: string) {
  run.attempt += 1;
  const id = (n: number) => `a${run.attempt}-${n}`;
  const update = (u: RunUpdate) => run.handlers.onUpdate?.(u);

  at(run, 200, () => update({ status: "running" }));

  toolCall(
    run,
    id(1),
    "check_git_history",
    { path: "app/", max_commits: 10, ...(reviewerFeedback ? { focus: reviewerFeedback } : {}) },
    [
      "a41c9e2 tune cache settings for staging parity",
      "9b07d15 add request timing to /predict-async",
      "5e1f3aa bump rq to 1.16",
    ],
    600,
    900,
  );

  toolCall(
    run,
    id(2),
    "read_prometheus_metrics",
    { metric: "inference_latency_seconds", quantile: 0.95, window: "1h" },
    { p95_ms: 4100, p95_ms_24h_ago: 2650, queue_depth: 14, workers_busy: "2/2" },
    1700,
    1200,
  );

  toolCall(
    run,
    id(3),
    "inspect_redis_cache",
    { pattern: "pred:*", stats: ["hit_ratio", "ttl_seconds"] },
    { keys_matched: 212, hit_ratio: 0.12, hit_ratio_24h_ago: 0.71, ttl_seconds_sample: [57, 12, 41] },
    3100,
    1000,
  );

  at(run, 4400, () => {
    const base =
      "Latency rose because the cache hit ratio fell from 71% to 12%. Commit a41c9e2 cut CACHE_TTL_SECONDS from 3600 to 60, so most requests now run full inference and the RQ queue backs up behind them.\n\nSuggested fix: restore the 3600 s TTL, or set TTLs per model.";
    update({ evidence: mockEvidence() });
    update({
      status: "pending_review",
      summary: reviewerFeedback
        ? `${base}\n\nRe-run with your instructions: "${reviewerFeedback}"`
        : base,
    });
  });
}

function subscribeMock(
  runId: string,
  onEvent: (event: ToolEvent) => void,
  handlers: RunStreamHandlers,
): () => void {
  const run = mockRuns.get(runId);
  if (!run) {
    handlers.onError?.("This demo run no longer exists. Start a new investigation.");
    return () => {};
  }

  clearTimers(run);
  run.attempt = 0;
  run.onEvent = onEvent;
  run.handlers = handlers;
  playInvestigation(run);

  return () => {
    clearTimers(run);
    run.onEvent = undefined;
    run.handlers = {};
  };
}

function mockDecision(runId: string, decision: GateDecision, feedback: string) {
  const run = mockRuns.get(runId);
  if (!run) return;

  if (decision === "approve") {
    at(run, 300, () => run.handlers.onUpdate?.({ status: "approved" }));
    at(run, 1700, () => run.handlers.onUpdate?.({ status: "completed" }));
  } else {
    at(run, 200, () => run.handlers.onUpdate?.({ status: "rejected" }));
    at(run, 1400, () => playInvestigation(run, feedback));
  }
}
