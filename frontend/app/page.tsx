"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Play } from "lucide-react";
import HumanGateCard from "@/components/HumanGateCard";
import LiveToolStream from "@/components/LiveToolStream";
import LoopStepper from "@/components/LoopStepper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { API_BASE, startWorkflow, submitGateDecision, subscribeToRunEvents } from "@/lib/api";
import {
  EMPTY_EVIDENCE,
  stepForStatus,
  type GateDecision,
  type RunUpdate,
  type ToolEvent,
  type WorkflowRun,
} from "@/types";

const DEFAULT_QUERY = "Why did async inference latency increase?";

const BLANK_RUN: WorkflowRun = {
  id: "",
  query: "",
  status: "idle",
  current_step: 1,
  tool_events: [],
  evidence: EMPTY_EVIDENCE,
  summary: "",
};

function countDiffFiles(diff: string): number {
  return diff.split("\n").filter((line) => line.startsWith("diff --git")).length;
}

export default function ControlPlane() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [run, setRun] = useState<WorkflowRun>(BLANK_RUN);
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const unsubscribe = useRef<(() => void) | null>(null);

  useEffect(() => () => unsubscribe.current?.(), []);

  const onToolEvent = useCallback((event: ToolEvent) => {
    setRun((prev) => {
      const exists = prev.tool_events.some((e) => e.id === event.id);
      return {
        ...prev,
        tool_events: exists
          ? prev.tool_events.map((e) => (e.id === event.id ? event : e))
          : [...prev.tool_events, event],
      };
    });
  }, []);

  const onUpdate = useCallback((update: RunUpdate) => {
    setRun((prev) => {
      const status = update.status ?? prev.status;
      return {
        ...prev,
        status,
        current_step: update.current_step ?? stepForStatus(status),
        summary: update.summary ?? prev.summary,
        evidence: update.evidence ?? prev.evidence,
      };
    });
  }, []);

  const start = async () => {
    unsubscribe.current?.();
    setError(null);
    setReviewNote("");
    setRun({ ...BLANK_RUN, query, status: "running", current_step: 2 });

    try {
      const { run_id, mock } = await startWorkflow(query);
      setDemo(mock);
      setRun((prev) => ({ ...prev, id: run_id }));
      unsubscribe.current = subscribeToRunEvents(run_id, onToolEvent, {
        onUpdate,
        onError: setError,
      });
    } catch (e) {
      setRun(BLANK_RUN);
      setError(e instanceof Error ? e.message : "Could not start the investigation.");
    }
  };

  const decide = async (decision: GateDecision, feedback: string) => {
    await submitGateDecision(run.id, decision, feedback);
    setReviewNote(feedback);
    // Optimistic: the stream confirms or overrides this with its own status events.
    onUpdate({ status: decision === "approve" ? "approved" : "rejected" });
  };

  const { status } = run;
  const running = status === "running";
  const inFlight = running || status === "approved" || status === "rejected";
  const handedOff = status === "approved" || status === "completed";
  const diffFiles = countDiffFiles(run.evidence.git_diff);

  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-10 sm:px-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">MedVision control plane</h1>
        <p className="max-w-prose text-sm leading-relaxed text-zinc-400">
          Give the agent a question, watch each tool call as it happens, and decide what moves forward. Nothing is
          handed off until you approve it.
        </p>
      </header>

      <Card className="border-zinc-800 bg-zinc-900/50">
        <CardContent className="grid gap-4 pt-6 md:grid-cols-[1fr_auto] md:items-end">
          <div className="space-y-1.5">
            <label htmlFor="query" className="text-sm font-medium text-zinc-300">
              Investigation query
            </label>
            <Textarea
              id="query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={2}
              className="border-zinc-700 bg-zinc-950"
            />
          </div>
          <Button
            onClick={start}
            disabled={inFlight || query.trim() === ""}
            className="bg-indigo-500 text-white hover:bg-indigo-400"
          >
            <Play className="mr-2 h-4 w-4" aria-hidden />
            {running ? "Investigating" : "Start investigation"}
          </Button>
        </CardContent>
        <p className="px-6 pb-5 text-xs text-zinc-500">
          Runs against the API at <span className="mono text-zinc-400">{API_BASE}</span>. If it isn&apos;t running,
          the page plays a simulated investigation instead.
          {demo && status !== "idle" && (
            <Badge variant="outline" className="ml-2 border-zinc-700 text-zinc-300">
              Demo data
            </Badge>
          )}
        </p>
      </Card>

      {error && (
        <p role="alert" className="rounded-md border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </p>
      )}

      <LoopStepper status={status} />

      <div className="grid gap-6 lg:grid-cols-2">
        <LiveToolStream events={run.tool_events} live={running} />
        <HumanGateCard status={status} summary={run.summary} evidence={run.evidence} onDecision={decide} />
      </div>

      {handedOff && (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
            <CardTitle className="text-base font-medium">Engineering output</CardTitle>
            <Badge
              variant="outline"
              className={
                status === "completed"
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                  : "border-indigo-400/40 text-indigo-300"
              }
            >
              {status === "completed" ? "Handed off" : "Handing off"}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-200">{run.summary}</p>
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              <div className="rounded-md border border-zinc-800 bg-zinc-950 p-3">
                <dt className="text-xs text-zinc-500">Tool calls</dt>
                <dd className="mono mt-1 text-zinc-100">{run.tool_events.length}</dd>
              </div>
              <div className="rounded-md border border-zinc-800 bg-zinc-950 p-3">
                <dt className="text-xs text-zinc-500">Diff attached</dt>
                <dd className="mono mt-1 text-zinc-100">
                  {diffFiles === 0 ? "None" : `${diffFiles} file${diffFiles === 1 ? "" : "s"}`}
                </dd>
              </div>
              <div className="rounded-md border border-zinc-800 bg-zinc-950 p-3">
                <dt className="text-xs text-zinc-500">Reviewer note</dt>
                <dd className="mt-1 text-zinc-100">{reviewNote || "None"}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
