"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Check, X } from "lucide-react";
import type { WorkflowStatus } from "@/types";

type StepState = "pending" | "active" | "done" | "rejected";

const STEPS = [
  { title: "Trigger", detail: "Issue or alert query" },
  { title: "Investigation", detail: "Active tool-calling loop" },
  { title: "Human review", detail: "Review and approval" },
  { title: "Output", detail: "Hand-off and diffs" },
] as const;

const STATES: Record<WorkflowStatus, StepState[]> = {
  idle: ["active", "pending", "pending", "pending"],
  running: ["done", "active", "pending", "pending"],
  pending_review: ["done", "done", "active", "pending"],
  rejected: ["done", "done", "rejected", "pending"],
  approved: ["done", "done", "done", "active"],
  completed: ["done", "done", "done", "done"],
};

// Border/text color and glow (as an r,g,b triple) for each step while it is the active one.
// Indigo for the bookend steps, cyan for the live investigation, amber for the human gate.
const ACTIVE = [
  { ring: "border-indigo-400 text-indigo-300", rgb: "129,140,248" },
  { ring: "border-cyan-400 text-cyan-300", rgb: "34,211,238" },
  { ring: "border-amber-400 text-amber-300", rgb: "251,191,36" },
  { ring: "border-indigo-400 text-indigo-300", rgb: "129,140,248" },
] as const;

function Marker({ index, state, pulse }: { index: number; state: StepState; pulse: boolean }) {
  const reduceMotion = useReducedMotion();
  const label = String(index + 1).padStart(2, "0");
  const base =
    "relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 text-sm font-semibold";

  if (state === "done") {
    return (
      <span className={`${base} border-emerald-500 bg-emerald-500 text-zinc-950`}>
        <Check className="h-5 w-5" aria-hidden />
      </span>
    );
  }

  if (state === "rejected") {
    return (
      <span className={`${base} border-rose-500 bg-rose-500/10 text-rose-300`}>
        <X className="h-5 w-5" aria-hidden />
      </span>
    );
  }

  if (state === "active") {
    const { ring, rgb } = ACTIVE[index];
    return (
      <span className={`${base} ${ring} bg-zinc-950`}>
        {pulse && !reduceMotion && (
          <motion.span
            aria-hidden
            className="absolute inset-0 rounded-full"
            animate={{
              boxShadow: [`0 0 0 0 rgba(${rgb},0.55)`, `0 0 0 12px rgba(${rgb},0)`],
            }}
            transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        {label}
      </span>
    );
  }

  return <span className={`${base} border-zinc-700 text-zinc-500`}>{label}</span>;
}

export default function LoopStepper({ status }: { status: WorkflowStatus }) {
  const states = STATES[status];

  return (
    <ol className="grid gap-5 md:grid-cols-4 md:gap-0" aria-label="Workflow progress">
      {STEPS.map((step, i) => {
        const state = states[i];
        const titleColor =
          state === "rejected" ? "text-rose-300" : state === "pending" ? "text-zinc-500" : "text-zinc-100";

        return (
          <li
            key={step.title}
            aria-current={state === "active" ? "step" : undefined}
            className="flex items-start gap-3 md:flex-col md:gap-0"
          >
            <div className="flex items-center md:w-full">
              <Marker index={i} state={state} pulse={status !== "idle"} />
              {i < STEPS.length - 1 && (
                <div className="mx-3 hidden h-0.5 flex-1 overflow-hidden rounded-full bg-zinc-800 md:block">
                  <motion.div
                    className="h-full origin-left bg-emerald-500"
                    initial={false}
                    animate={{ scaleX: state === "done" ? 1 : 0 }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                  />
                </div>
              )}
            </div>
            <div className="md:mt-3 md:pr-4">
              <p className={`text-sm font-medium ${titleColor}`}>
                {step.title}
                <span className="sr-only"> ({state})</span>
              </p>
              <p className="text-xs text-zinc-500">
                {state === "rejected" ? "Rejected by reviewer" : step.detail}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
