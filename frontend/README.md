# MedVision control plane (frontend)

Web control plane for the MedVision V3 human-in-the-loop agentic platform. It shows the four-step loop (Trigger, Investigation, Human Gate, Output), streams the agent's tool calls live, and puts an approve/reject gate in front of the hand-off.

Without a backend it plays a simulated investigation, so the demo runs anywhere.

> **Status:** these files were written but not compiled, type-checked or run. The sandbox that produced them could not reach the npm registry. Run `npm run build` once after setup and fix anything it reports before you record a demo.

## Stack

Next.js 14 (App Router), TypeScript, Tailwind CSS v3, Framer Motion, Lucide, shadcn/ui.

## Setup

These files are the app code only. Create the Next.js project first, then copy them in.

```bash
# 1. New project. Use @14 so you get Tailwind v3 (the @tailwind directives in globals.css need it).
npx create-next-app@14 frontend --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*"
cd frontend

# 2. shadcn/ui (accept the defaults, pick the "Slate" or "Zinc" base colour, use CSS variables)
npx shadcn@latest init
npx shadcn@latest add card button badge tabs dialog textarea input

# 3. Animation and icons
npm i framer-motion lucide-react
```

If the latest shadcn CLI asks you to move to Tailwind v4, decline or pin an older CLI release (`npx shadcn@2.3.0 ...`). This app is written for Tailwind v3.

Then copy these folders from this package over the generated project, replacing files when asked:

```
app/        layout.tsx, page.tsx, globals.css
components/ LoopStepper.tsx, LiveToolStream.tsx, HumanGateCard.tsx, EvidenceViewer.tsx
lib/        api.ts
types/      index.ts
```

Keep the `components/ui/` folder that shadcn generated. Do not overwrite it.

Check `tailwind.config.ts` after `shadcn init`. The shadcn colour mapping (`background`, `border`, `primary` and so on, all pointing at `hsl(var(--...))`) must still be there, because `globals.css` uses `border-border` and the shadcn components rely on those tokens. `globals.css` defines the dark theme values itself, and `layout.tsx` sets `className="dark"` on `<html>`.

```bash
npm run dev     # http://localhost:3000
npm run build   # type-check and production build
```

## Environment variables

Create `.env.local` if you need either one:

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api` | Backend base URL |
| `NEXT_PUBLIC_USE_MOCK` | unset | Set to `true` to always use the simulated run, even if a backend is up |

## Mock fallback

`startWorkflow` tries the backend with a 3 second timeout. If it can't connect, the page switches to a simulated run and shows a "Demo data" badge. The simulation emits `check_git_history`, `read_prometheus_metrics` and `inspect_redis_cache` calls, then evidence and a `pending_review` status. Approving completes the run. Rejecting re-runs the investigation using your feedback.

If the backend is reachable but returns an HTTP error, the page shows that error. It does not fall back silently, so a broken backend isn't hidden by fake data.

## Backend contract

All paths are relative to `API_BASE`.

**Start a run**

```
POST /workflows
{ "query": "Why did async inference latency increase?" }
-> { "run_id": "abc123" }
```

**Stream events** (Server-Sent Events)

```
GET /workflows/{run_id}/events
```

| Event name | Data (JSON) |
| --- | --- |
| `tool_event` | `ToolEvent`: `id`, `tool_name`, `input_params`, `output_data?`, `status` (`running`, `success`, `failed`), `timestamp`. Re-send the same `id` to update a call (for example running to success). |
| `status` | `{ "status": "running" \| "pending_review" \| "approved" \| "rejected" \| "completed", "current_step"?: 1-4, "summary"?: string }` |
| `evidence` | `{ "logs": string[], "metrics": Record<string, number>, "git_diff": string }`, optionally with `summary` |

End the stream by sending `status` with `completed`. The client closes the connection when it sees it.

**Gate decision**

```
POST /workflows/{run_id}/gate
{ "decision": "approve" | "reject", "feedback": "optional for approve, required for reject" }
```

The gate card sends the decision, then updates optimistically. Your `status` events confirm or override that.

## Layout

```
app/page.tsx                    dashboard: query box, stepper, stream + gate, output
components/LoopStepper.tsx      4-step progress with glow (amber for the human gate)
components/LiveToolStream.tsx   terminal-style tool call log with expandable payloads
components/HumanGateCard.tsx    review card: findings, evidence, feedback, approve/reject
components/EvidenceViewer.tsx   Metrics / Logs / Git diff tabs
lib/api.ts                      startWorkflow, submitGateDecision, subscribeToRunEvents, mock engine
types/index.ts                  WorkflowStatus, ToolEvent, Evidence, WorkflowRun and helpers
```

## Accessibility

The tool stream is a live `role="log"` region, expandable rows are real buttons with `aria-expanded`, and glow and spinner animations stop when the OS asks for reduced motion.
