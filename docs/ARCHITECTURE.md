# MedVision AI V3 Architecture

## 1. Purpose

V3 is a separate agentic engineering system built around the existing MedVision V2 repository.

V2 remains the production-oriented inference platform. V3 provides bounded investigation, implementation, testing, and engineering assistance around that system.

## 2. Human Control Principle

Humans retain authority over:

- architecture decisions
- high-impact changes
- production-impacting actions
- merge decisions
- deployment decisions

Agents may perform bounded engineering work under explicit policy.

## 3. General Agent Architecture

```text
                         HUMAN
                           │
                           │ task
                           ▼
                    ORCHESTRATOR
                           │
                     WORKFLOW STATE
                           │
                           ▼
                         AGENT
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
               TOOLS               POLICY
                 │                   │
                 └─────────┬─────────┘
                           ▼
                    LLM / reasoning
                           │
                           ▼
                         RESULT
                           │
                           ▼
                     HUMAN REVIEW
```

## 4. Core Terminology

### AgentTask

A structured representation of the work requested by a human.

### AgentState

Information accumulated by an agent during the current task, such as observations, findings, tool calls, and errors.

### WorkflowState

The current state of the overall engineering workflow, such as `CREATED`, `INVESTIGATING`, `WAITING_FOR_REVIEW`, or `COMPLETED`.

### Tool

A bounded capability exposed to an agent, such as reading a file, searching a repository, inspecting Git history, or running tests.

### Tool Registry

The controlled collection of tools available to an agent.

### Policy

Rules defining what an agent is permitted to do. Tools provide capabilities; policies constrain those capabilities.

### Sandbox

An isolated execution boundary for risky work. The first implementation will use Git worktrees for coding tasks. A stronger process/container sandbox may be considered later.

### Human Review Gate

A mandatory control point where a human can approve, reject, or request changes before consequential work continues.

## 5. V2/V3 Repository Isolation

V2 and V3 are separate Git repositories:

```text
/Users/<user>/
├── MedVision-AI-v2.0-Production-AI-Inference-Platform/
│   └── .git/
└── MedVision-AI-v3-Agentic-Engineering-Platform/
    └── .git/
```

V3 references V2 by filesystem path. It does not copy V2 into the V3 repository.

The future Coding Agent will use a Git worktree derived from V2 rather than modifying `V2/main` directly.

## 6. Agent Runtime Evolution

Phase 0:

```text
Human
  ↓
Orchestrator
  ↓
Agent
  ↓
Python tools
  ↓
Result
```

Phase 3:

```text
Human
  ↓
Orchestrator
  ↓
Agent
  ↓
LLM decides next action
  ↓
Tool Registry
  ↓
Python tool
  ↓
Tool result
  ↓
LLM
  ↓
...
  ↓
Final result
```

MCP will be considered later as a standardized tool-access layer. It is not required for the initial agent runtime.

## 7. Architectural Decision Log

### ADR-001 — Start without an agent framework

**Decision:** Implement the first runtime in plain Python.

**Reason:** Understand state, tool calling, control loops, policies, and human approval before introducing abstractions such as LangGraph or CrewAI.

### ADR-002 — Keep V2 and V3 repositories independent

**Decision:** V3 must not be merged into V2.

**Reason:** V2 represents the completed inference platform; V3 represents a separate engineering-control layer.

### ADR-003 — Protect V2 main during agent coding

**Decision:** Coding agents will operate in isolated Git worktrees.

**Reason:** The agent must be structurally prevented from directly modifying V2's main working tree.
