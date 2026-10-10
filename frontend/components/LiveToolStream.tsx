"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { CheckCircle2, ChevronRight, Loader2, Terminal, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ToolEvent, ToolStatus } from "@/types";

const STATUS_STYLE: Record<ToolStatus, { label: string; className: string }> = {
  running: { label: "Running", className: "border-cyan-400/40 bg-cyan-400/10 text-cyan-300" },
  success: { label: "Success", className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" },
  failed: { label: "Failed", className: "border-rose-500/40 bg-rose-500/10 text-rose-300" },
};

function StatusBadge({ status }: { status: ToolStatus }) {
  const { label, className } = STATUS_STYLE[status];
  return (
    <Badge variant="outline" className={`shrink-0 gap-1 font-medium ${className}`}>
      {status === "running" && <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden />}
      {status === "success" && <CheckCircle2 className="h-3 w-3" aria-hidden />}
      {status === "failed" && <XCircle className="h-3 w-3" aria-hidden />}
      {label}
    </Badge>
  );
}

function summarizeParams(params: Record<string, unknown>): string {
  return Object.entries(params)
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(", ");
}

function formatPayload(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("en-GB");
}

function Payload({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="mb-1 text-xs text-zinc-500">{label}</p>
      <pre className="mono max-h-56 overflow-auto whitespace-pre-wrap break-words rounded border border-zinc-800 bg-zinc-950 p-2 text-xs leading-relaxed text-zinc-300">
        {formatPayload(value)}
      </pre>
    </div>
  );
}

export default function LiveToolStream({ events, live }: { events: ToolEvent[]; live: boolean }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const scroller = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
  }, [events, reduceMotion]);

  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <Card className="flex h-full flex-col border-zinc-800 bg-zinc-900/50">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base font-medium">
          <Terminal className="h-4 w-4 text-cyan-400" aria-hidden />
          Tool calls
          {events.length > 0 && <span className="text-sm font-normal text-zinc-500">{events.length}</span>}
        </CardTitle>
        {live && (
          <Badge variant="outline" className="border-cyan-400/40 text-cyan-300">
            Streaming
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex-1">
        <div
          ref={scroller}
          role="log"
          aria-live="polite"
          aria-label="Tool call stream"
          className="mono h-[420px] overflow-y-auto rounded-md border border-zinc-800 bg-zinc-950 p-2"
        >
          {events.length === 0 ? (
            <p className="px-3 py-16 text-center font-sans text-sm text-zinc-500">
              No tool calls yet. Start an investigation and each call appears here as the agent makes it.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {events.map((event) => {
                const isOpen = open.has(event.id);
                return (
                  <motion.li
                    key={event.id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18 }}
                    className="rounded-md border border-zinc-800/80 bg-zinc-900/40"
                  >
                    <button
                      type="button"
                      onClick={() => toggle(event.id)}
                      aria-expanded={isOpen}
                      aria-controls={`payload-${event.id}`}
                      className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-indigo-400"
                    >
                      <ChevronRight
                        className={`h-4 w-4 shrink-0 text-zinc-500 transition-transform motion-reduce:transition-none ${isOpen ? "rotate-90" : ""}`}
                        aria-hidden
                      />
                      <span className="shrink-0 text-sm text-cyan-300">
                        <span className="text-zinc-600" aria-hidden>
                          ${" "}
                        </span>
                        {event.tool_name}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-xs text-zinc-500">
                        {summarizeParams(event.input_params)}
                      </span>
                      <StatusBadge status={event.status} />
                      <time dateTime={event.timestamp} className="hidden shrink-0 text-xs text-zinc-500 sm:block">
                        {formatTime(event.timestamp)}
                      </time>
                    </button>
                    {isOpen && (
                      <div id={`payload-${event.id}`} className="space-y-3 border-t border-zinc-800 px-3 py-3">
                        <Payload label="Input" value={event.input_params} />
                        {event.output_data !== undefined && <Payload label="Output" value={event.output_data} />}
                      </div>
                    )}
                  </motion.li>
                );
              })}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
