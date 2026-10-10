"use client";

import { useState } from "react";
import { Check, ShieldCheck, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import EvidenceViewer from "@/components/EvidenceViewer";
import type { Evidence, GateDecision, WorkflowStatus } from "@/types";

interface HumanGateCardProps {
  status: WorkflowStatus;
  summary: string;
  evidence: Evidence;
  onDecision: (decision: GateDecision, feedback: string) => Promise<void>;
}

const STATUS_BADGE: Record<WorkflowStatus, { label: string; className: string }> = {
  idle: { label: "Not ready", className: "border-zinc-700 text-zinc-400" },
  running: { label: "Not ready", className: "border-zinc-700 text-zinc-400" },
  pending_review: { label: "Waiting for you", className: "border-amber-400/50 bg-amber-400/10 text-amber-300" },
  approved: { label: "Approved", className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" },
  completed: { label: "Approved", className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" },
  rejected: { label: "Rejected", className: "border-rose-500/40 bg-rose-500/10 text-rose-300" },
};

export default function HumanGateCard({ status, summary, evidence, onDecision }: HumanGateCardProps) {
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState<GateDecision | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pending = status === "pending_review";
  const decided = status === "approved" || status === "completed";
  const badge = STATUS_BADGE[status];

  async function decide(decision: GateDecision) {
    setBusy(decision);
    setError(null);
    try {
      await onDecision(decision, feedback.trim());
      setRejectOpen(false);
      setFeedback("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not record your decision. Try again.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className={`h-full border-zinc-800 bg-zinc-900/50 ${pending ? "ring-1 ring-amber-400/50" : ""}`}>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base font-medium">
          <ShieldCheck className="h-4 w-4 text-amber-400" aria-hidden />
          Human review
        </CardTitle>
        <Badge variant="outline" className={badge.className}>
          {badge.label}
        </Badge>
      </CardHeader>

      <CardContent className="space-y-4">
        {(status === "idle" || status === "running") && (
          <p className="py-10 text-center text-sm text-zinc-500">
            The agent hasn&apos;t submitted findings yet. Review opens here when its investigation finishes.
          </p>
        )}

        {status === "rejected" && (
          <p className="py-10 text-center text-sm text-zinc-400">
            You rejected this result. Nothing was handed off, and the agent is investigating again with your
            instructions.
          </p>
        )}

        {(pending || decided) && (
          <>
            <section aria-labelledby="findings-heading" className="space-y-2">
              <h3 id="findings-heading" className="text-sm font-medium text-zinc-300">
                Agent findings
              </h3>
              <p className="whitespace-pre-line rounded-md border border-zinc-800 bg-zinc-950/70 p-3 text-sm leading-relaxed text-zinc-200">
                {summary}
              </p>
            </section>

            <EvidenceViewer evidence={evidence} />

            {pending && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label htmlFor="gate-feedback" className="text-sm font-medium text-zinc-300">
                    Instructions for the agent
                  </label>
                  <Textarea
                    id="gate-feedback"
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    rows={3}
                    placeholder="Optional when approving. Required when rejecting, so the agent knows what to change."
                    className="border-zinc-700 bg-zinc-950"
                  />
                </div>

                {error && (
                  <p role="alert" className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                    {error}
                  </p>
                )}

                <div className="grid gap-3 sm:grid-cols-2">
                  <Button
                    onClick={() => decide("approve")}
                    disabled={busy !== null}
                    className="bg-emerald-600 text-white hover:bg-emerald-500"
                  >
                    <Check className="mr-2 h-4 w-4" aria-hidden />
                    Approve &amp; Hand-off
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setRejectOpen(true)}
                    disabled={busy !== null}
                    className="border-rose-500/60 bg-transparent text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
                  >
                    <X className="mr-2 h-4 w-4" aria-hidden />
                    Reject &amp; Re-investigate
                  </Button>
                </div>
              </div>
            )}

            {decided && (
              <p className="text-sm text-zinc-400">
                You approved this result{status === "approved" ? ". Handing it off now." : " and it was handed off."}
              </p>
            )}
          </>
        )}
      </CardContent>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent className="border-zinc-800 bg-zinc-900 text-zinc-100">
          <DialogHeader>
            <DialogTitle>Reject and re-investigate?</DialogTitle>
            <DialogDescription>
              Nothing from this result is handed off. The agent runs the investigation again using your
              instructions.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <label htmlFor="reject-feedback" className="text-sm font-medium text-zinc-300">
              What should the agent do differently?
            </label>
            <Textarea
              id="reject-feedback"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              rows={4}
              placeholder="For example: check the queue depth before blaming the cache."
              className="border-zinc-700 bg-zinc-950"
            />
          </div>
          {error && (
            <p role="alert" className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
              {error}
            </p>
          )}
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="ghost" onClick={() => setRejectOpen(false)} disabled={busy !== null}>
              Keep reviewing
            </Button>
            <Button
              onClick={() => decide("reject")}
              disabled={busy !== null || feedback.trim() === ""}
              className="bg-rose-600 text-white hover:bg-rose-500"
            >
              Reject &amp; Re-investigate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
