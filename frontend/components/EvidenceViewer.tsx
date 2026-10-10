"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Evidence } from "@/types";

const formatMetricName = (key: string) => key.replace(/_/g, " ");

const formatMetricValue = (value: number) =>
  Number.isInteger(value) ? value.toLocaleString("en-US") : value.toFixed(2);

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ") || line.startsWith("index ")) {
    return "text-zinc-400";
  }
  if (line.startsWith("@@")) return "bg-cyan-500/10 text-cyan-300";
  if (line.startsWith("+")) return "bg-emerald-500/10 text-emerald-300";
  if (line.startsWith("-")) return "bg-rose-500/10 text-rose-300";
  return "text-zinc-400";
}

function countChanges(diff: string) {
  let added = 0;
  let removed = 0;
  for (const line of diff.split("\n")) {
    if (line.startsWith("+") && !line.startsWith("+++")) added += 1;
    else if (line.startsWith("-") && !line.startsWith("---")) removed += 1;
  }
  return { added, removed };
}

function Empty({ children }: { children: string }) {
  return <p className="rounded-md border border-dashed border-zinc-800 py-8 text-center text-sm text-zinc-500">{children}</p>;
}

export default function EvidenceViewer({ evidence }: { evidence: Evidence }) {
  const metrics = Object.entries(evidence.metrics);
  const diff = evidence.git_diff.trim();
  const { added, removed } = countChanges(diff);

  return (
    <Tabs defaultValue="metrics" className="w-full">
      <TabsList className="border border-zinc-800 bg-zinc-900">
        <TabsTrigger value="metrics">Metrics</TabsTrigger>
        <TabsTrigger value="logs">Logs</TabsTrigger>
        <TabsTrigger value="diff">Git diff</TabsTrigger>
      </TabsList>

      <TabsContent value="metrics">
        {metrics.length === 0 ? (
          <Empty>No metrics were recorded for this run.</Empty>
        ) : (
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {metrics.map(([key, value]) => (
              <div key={key} className="rounded-md border border-zinc-800 bg-zinc-950 p-3">
                <dt className="text-xs text-zinc-500">{formatMetricName(key)}</dt>
                <dd className="mono mt-1 text-lg text-zinc-100">{formatMetricValue(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </TabsContent>

      <TabsContent value="logs">
        {evidence.logs.length === 0 ? (
          <Empty>No logs yet. They appear once the agent submits its findings.</Empty>
        ) : (
          <pre className="mono max-h-64 overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-300">
            {evidence.logs.join("\n")}
          </pre>
        )}
      </TabsContent>

      <TabsContent value="diff">
        {diff === "" ? (
          <Empty>No diff attached to this result.</Empty>
        ) : (
          <div className="overflow-hidden rounded-md border border-zinc-800">
            <p className="border-b border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-400">
              <span className="text-emerald-300">+{added}</span> <span className="text-rose-300">-{removed}</span>
            </p>
            <pre className="mono max-h-64 overflow-auto bg-zinc-950 py-1 text-xs leading-relaxed">
              <code className="block min-w-max">
                {diff.split("\n").map((line, i) => (
                  <span key={i} className={`block px-3 ${diffLineClass(line)}`}>
                    {line || " "}
                  </span>
                ))}
              </code>
            </pre>
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
}
