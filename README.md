# MedVision AI V3 — Agentic Engineering Platform

MedVision AI V3 is a human-in-the-loop agentic engineering layer built around the MedVision AI V2 production inference platform.

## V2 → V3

V2 is the production-oriented inference system:

- Model Registry
- Inference execution
- Async DB executor
- Redis caching
- RQ workers
- JWT authentication

V3 does **not** replace or merge into V2. It is a separate repository that can investigate and perform bounded engineering work against a controlled V2 working copy.

## Core Principle

> Humans control architecture and high-impact decisions. Agents handle bounded investigation, implementation, testing, and repetitive engineering work.

```text
                         HUMAN
                           │
                           │ engineering task
                           ▼
                    ORCHESTRATOR
                           │
                     WORKFLOW STATE
                           │
                           ▼
                         AGENT
                           │
                 ┌─────────┴─────────┐
                 │                   │
               STATE               POLICY
                 │                   │
                 └─────────┬─────────┘
                           ▼
                    LLM / reasoning
                           │
                           ▼
                     TOOL REGISTRY
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
             Git         Files        Tests
              │            │            │
              └────────────┼────────────┘
                           ▼
                         RESULT
                           │
                           ▼
                     HUMAN REVIEW
```

## Development Philosophy

V3 initially uses plain Python rather than LangChain, LangGraph, CrewAI, or MCP. The purpose is to understand and implement the underlying agent runtime first: state, tools, policies, orchestration, control loops, and human approval gates.

Frameworks and MCP may be introduced later when there is a concrete architectural reason to use them.

## Repository Boundary

V2 and V3 remain independent Git repositories. V3 must never directly modify `V2/main`.

When a future Coding Agent needs to change V2, it will operate through an isolated Git worktree/sandbox and produce a reviewable diff.

## Roadmap

- Phase 0 — Agent Runtime Foundation
- Phase 1 — Investigation Agent
- Phase 2 — Human Review / Control Plane
- Phase 3 — LLM Tool-Calling Loop
- Phase 4 — Bounded Coding Agent + Git Worktree
- Phase 5 — Test Agent
- Phase 6 — Multi-Agent Orchestration
- Phase 7 — Performance Investigation Agent
- Phase 8 — MCP Tool Layer
- Phase 9 — Agent Evaluation and Observability
- Phase 10 — Framework comparison: custom runtime vs LangGraph/CrewAI
