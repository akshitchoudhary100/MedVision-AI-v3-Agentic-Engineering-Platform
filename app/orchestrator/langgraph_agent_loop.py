from __future__ import annotations
from uuid import uuid4
import json
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.llm.base import BaseLLM
from app.policies.base import BasePolicy
from app.tools.registry import ToolRegistry


LoopStatus = Literal["running", "tool_pending", "tool_ready", "tool_result_ready", "completed", "failed"]


class AgentLoopState(TypedDict, total=False):
    """JSON-friendly state for one LangGraph-controlled investigation loop."""

    query: str
    repo_path: str
    status: LoopStatus
    messages: list[dict[str, Any]]
    pending_tool_call: dict[str, Any] | None
    validated_tool_call: dict[str, Any] | None
    current_tool_name: str
    current_tool_arguments: dict[str, Any]
    current_tool_repo_relative_path: str
    current_symbol_key: str
    last_tool_result: str
    last_tool_succeeded: bool
    last_search_paths: list[str]
    step_count: int
    max_steps: int
    max_search_calls: int
    max_source_files: int
    min_source_files: int
    search_count: int
    files_seen_in_search: list[str]
    files_read: list[str]
    queries_used: list[str]
    symbols_read: list[str]
    tool_calls: list[str]
    errors: list[str]
    summary: str
    findings: list[str]
    evidence: list[str]


def _normalize_query(query: str) -> str:
    return " ".join(query.lower().strip().split())


def _repo_relative_path(path: str, repo_path: str) -> str:
    """Return a repository-relative path or reject paths outside the repo."""
    repo = Path(repo_path).expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = repo / candidate
    resolved = candidate.resolve()
    try:
        return resolved.relative_to(repo).as_posix()
    except ValueError as exc:
        raise ValueError(f"Path is outside the investigation repository: {path}") from exc


def _absolute_repo_path(path: str, repo_path: str) -> str:
    relative = _repo_relative_path(path, repo_path)
    return (Path(repo_path).expanduser().resolve() / relative).as_posix()


def _serialize_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    if hasattr(result, "as_text"):
        return str(result.as_text())
    try:
        return json.dumps(result, indent=2, default=str)
    except (TypeError, ValueError):
        return str(result)


def _system_prompt(state: AgentLoopState) -> str:
    return f"""You are a software repository investigation agent.

    Task:
    {state.get('query', '')}

    Repository:
    {state.get('repo_path', '')}

    Available tools:
    - search_code
    - read_symbol
    - read_file
    - git_log

    Investigate the repository dynamically using source-code evidence.

    IMPORTANT INVESTIGATION BEHAVIOR:

    Before choosing a tool, explicitly determine:

    1. action_reason:
    Why is this tool useful RIGHT NOW?
    2. expected_information:
    What specific information do you expect to obtain from this tool?
    3. completion_criteria:
    What evidence would make you confident that the investigation is complete?
    4. missing_evidence:
    What important evidence is still missing?

    TOOL CALL CONTRACT:

    When calling a tool, follow that tool's supplied JSON schema exactly.

    - search_code requires query and root_path.
    - read_file requires path.
    - read_symbol requires file, symbol_name, and root_path.
    - Do not put diagnostic metadata or explanations inside tool arguments.
    - Include every required argument with the correct name and type.
    - Do not invent or reconstruct the repository root. Use the supplied
      repository context and repository-relative paths where requested.

    A search result is not evidence until its source is inspected with
    read_file or read_symbol.

    Never invent files, functions, variables, endpoints, configuration,
    or implementation details.

    Never repeat a search query.

    Make subsequent searches more specific based on what you learned.

    After every tool observation, reconsider:
    - what evidence has been obtained,
    - what evidence is still missing,
    - whether another tool is actually necessary,
    - and whether the investigation now satisfies the completion criteria.

    IMPORTANT:
    Do not produce a final answer merely because you can write a plausible answer.

    A final answer is valid only when:
    - the answer is grounded in inspected source code,
    - the required minimum source-file evidence has been inspected,
    - the evidence actually supports the requested conclusion,
    - and there is no important unresolved evidence gap.

    If the runtime tells you that your final answer was rejected because
    additional evidence is required, do NOT simply rewrite the same answer.
    Identify the missing evidence and obtain genuinely new source evidence.

    Runtime limits:
    - Maximum search calls: {state.get('max_search_calls', 3)}
    - Maximum distinct source files inspected: {state.get('max_source_files', 4)}
    - Minimum distinct source files required before final answer: {state.get('min_source_files', 2)}
    - Maximum LLM reasoning calls: {state.get('max_steps', 12)}

    The runtime—not you—enforces tool permissions, budgets, repository path
    boundaries, and evidence requirements.

    Choose the next useful investigation action based on the current evidence.
    Do not assume a fixed tool sequence.
    """


def _tool_feedback(
    state: AgentLoopState,
    message: str,
    *,
    name: str | None = None,
    arguments: dict[str, Any] | None = None,
    record_error: bool = False,
) -> dict[str, Any]:
    """Stage a failed/denied tool response for the observe node to append once."""
    tool_name = name or str((state.get("pending_tool_call") or {}).get("name", "unknown"))
    update: dict[str, Any] = {
        "status": "tool_result_ready",
        "current_tool_name": tool_name,
        "current_tool_arguments": dict(arguments or {}),
        "last_tool_result": message,
        "last_tool_succeeded": False,
        "last_search_paths": [],
    }
    if record_error:
        update["errors"] = [*state.get("errors", []), message]
    return update


def _parse_model_response(
        raw: Any,
    ) -> tuple[str, dict[str, Any] | None, str, dict[str, Any]]:
        if not isinstance(raw, dict):
            raise ValueError("Invalid LLM response: expected an object.")

        message = raw.get("message", {})
        if not isinstance(message, dict):
            raise ValueError("Invalid LLM response: 'message' must be an object.")

        tool_calls = message.get("tool_calls") or []

        if tool_calls:
            first = tool_calls[0]

            if not isinstance(first, dict) or not isinstance(
                first.get("function"), dict
            ):
                raise ValueError("Invalid tool-call structure.")

            function = first["function"]
            name = function.get("name")
            raw_arguments = function.get("arguments", {})

            if not isinstance(name, str) or not name.strip():
                raise ValueError("Tool call has no valid function name.")

            if isinstance(raw_arguments, str):
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Tool arguments for {name!r} are invalid JSON."
                    ) from exc
            else:
                arguments = raw_arguments

            if not isinstance(arguments, dict):
                raise ValueError(
                    f"Tool arguments for {name!r} must be a JSON object."
                )

            # Ollama responses may not include an ID. The internal protocol
            # always supplies one, and each resulting tool message reuses it.
            call_id = first.get("id") or f"local_{uuid4().hex}"

            normalized_call = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": arguments,
                },
            }

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": [normalized_call],
            }

            if message.get("thinking"):
                assistant_message["thinking"] = message["thinking"]

            return (
                "tool_call",
                {
                    "id": call_id,
                    "name": name,
                    "arguments": arguments,
                },
                "",
                assistant_message,
            )

        content = message.get("content", "")

        if not isinstance(content, str):
            raise ValueError("LLM returned a non-text final answer.")

        assistant_message = {
            "role": "assistant",
            "content": content,
        }

        if message.get("thinking"):
            assistant_message["thinking"] = message["thinking"]

        return "final", None, content.strip(), assistant_message


def _initialize(
    state: AgentLoopState,
    *,
    max_steps: int = 5,
    max_search_calls: int = 3,
    max_source_files: int = 4,
    min_source_files: int = 2,
) -> dict[str, Any]:
    query = str(state.get("query", "")).strip()
    repo_path = str(state.get("repo_path", "")).strip()
    if not query:
        return {"status": "failed", "errors": [*state.get("errors", []), "Investigation query cannot be empty."]}
    if not repo_path:
        return {"status": "failed", "errors": [*state.get("errors", []), "A repository path is required."]}
    return {
        "query": query,
        "repo_path": str(Path(repo_path).expanduser().resolve()),
        "status": "running",
        "messages": list(state.get("messages", [])),
        "pending_tool_call": None,
        "validated_tool_call": None,
        "last_tool_result": "",
        "last_tool_succeeded": False,
        "last_search_paths": [],
        "step_count": 0,
        "max_steps": int(state.get("max_steps", max_steps)),
        "max_search_calls": int(state.get("max_search_calls", max_search_calls)),
        "max_source_files": int(state.get("max_source_files", max_source_files)),
        "min_source_files": int(state.get("min_source_files", min_source_files)),
        "search_count": 0,
        "files_seen_in_search": [],
        "files_read": [],
        "queries_used": [],
        "symbols_read": [],
        "tool_calls": [],
        "errors": list(state.get("errors", [])),
        "summary": "",
        "findings": list(state.get("findings", [])),
        "evidence": [],
    }


def _route_after_initialize(state: AgentLoopState) -> str:
    return "reason" if state.get("status") == "running" else END


def _reason(state: AgentLoopState, *, llm: BaseLLM, tools: ToolRegistry) -> dict[str, Any]:
    current_step = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 5))
    if current_step >= max_steps:
        error = f"Agent stopped after reaching the maximum reasoning-step budget ({max_steps}) without a valid final answer."
        return {"status": "failed", "errors": [*state.get("errors", []), error]}

    messages = [
        {"role": "system", "content": _system_prompt(state)},
        {"role": "user", "content": state.get("query", "")},
        *state.get("messages", []),
    ]
    try:
        raw = llm.generate(messages=messages, tools=tools.definitions())
        response_type, call, answer, assistant_message = _parse_model_response(raw)

        content = str(assistant_message.get("content") or "").strip()

        next_step = current_step + 1

        print("\n========== AGENT DECISION ==========")
        print(f"STEP: {next_step}")
        print(f"TYPE: {response_type}")
        print(f"TOOL: {(call or {}).get('name')}")
        print(f"ARGUMENTS: {(call or {}).get('arguments')}")
        print(f"INSPECTED: {state.get('files_read', [])}")
        print(f"ACTION METADATA: {content}")
        print("====================================\n")

        
    except Exception as exc:
        return {
            "status": "failed",
            "step_count": current_step + 1,
            "errors": [*state.get("errors", []), f"LLM reasoning failed: {exc}"],
        }

    next_messages = list(state.get("messages", []))
    next_messages.append(assistant_message)
    next_step = current_step + 1

    if response_type == "tool_call" and call is not None:
        return {
            "status": "tool_pending",
            "step_count": next_step,
            "messages": next_messages,
            "pending_tool_call": call,
            "validated_tool_call": None,
        }

    if not answer:
        next_messages.append({"role": "user", "content": "Your answer was empty. Continue the investigation or provide the evidence-based final answer."})
        return {"status": "running", "step_count": next_step, "messages": next_messages}

    inspected = set(state.get("files_read", []))
    minimum = int(state.get("min_source_files", 2))
    if len(inspected) < minimum:
        next_messages.append({
            "role": "user",
            "content": (
                "RUNTIME VALIDATION RESULT:\n"
                "Your proposed final answer was rejected.\n\n"
                f"Inspected source files: {len(inspected)}\n"
                f"Required source files: {minimum}\n"
                f"Already inspected: {sorted(inspected)}\n\n"
                "You are NOT finished.\n"
                "Identify the missing evidence required to support your answer.\n"
                "Then choose a tool that obtains genuinely new evidence.\n"
                "Do not repeat the previous answer.\n"
                "Do not repeat a search unless the query is materially more specific."
            ),
        })
        return {"status": "running", "step_count": next_step, "messages": next_messages}

    return {
        "status": "completed",
        "step_count": next_step,
        "messages": next_messages,
        "summary": answer,
        "evidence": sorted(inspected),
    }


def _route_after_reason(state: AgentLoopState) -> str:
    status = state.get("status")
    if status == "tool_pending":
        return "validate_tool"
    if status == "running":
        return "reason"
    return END


def _validate_tool(state: AgentLoopState, *, policy: BasePolicy, tools: ToolRegistry) -> dict[str, Any]:
    call = state.get("pending_tool_call") or {}
    name = str(call.get("name", ""))
    arguments = call.get("arguments", {})
    repo_path = state.get("repo_path", "")
    if not isinstance(arguments, dict):
        return _tool_feedback(
            state,
            "Tool arguments must be a JSON object.",
            name=name or "unknown",
        )

    def deny(message: str, *, record_error: bool = False) -> dict[str, Any]:
        return _tool_feedback(
            state,
            message,
            name=name or "unknown",
            arguments=arguments,
            record_error=record_error,
        )

    if not name or not policy.is_allowed(name):
        return deny(
            f"Tool '{name or '<missing>'}' is not allowed by policy.",
            record_error=True,
        )
    if name not in tools.list_tools():
        return deny(f"Unknown tool '{name}'. Available tools: {tools.list_tools()}")

    normalized = dict(arguments)
    current_path = ""
    symbol_key = ""

    if name == "search_code":
        query = str(normalized.get("query", "")).strip()
        if not query:
            return deny("search_code requires a non-empty 'query'.")
        normalized_query = _normalize_query(query)
        queries_used = list(state.get("queries_used", []))
        if normalized_query in queries_used:
            return deny(f"You already searched for '{query}'. Use a more specific query based on evidence learned.")
        if int(state.get("search_count", 0)) >= int(state.get("max_search_calls", 3)):
            return deny("Search call budget exhausted.")
        normalized["root_path"] = repo_path
        return {
            "status": "tool_ready",
            "current_tool_name": name,
            "current_tool_arguments": normalized,
            "validated_tool_call": {"name": name, "arguments": normalized},
            "current_tool_repo_relative_path": "",
            "current_symbol_key": "",
            "queries_used": [*queries_used, normalized_query],
            "search_count": int(state.get("search_count", 0)) + 1,
        }

    if name == "read_file":
        path = normalized.get("path")
        if not path:
            return deny("read_file requires 'path'.")
        try:
            current_path = _repo_relative_path(str(path), repo_path)
            normalized["path"] = _absolute_repo_path(str(path), repo_path)
        except (OSError, ValueError) as exc:
            return deny(str(exc))
        discovered = set(state.get("files_seen_in_search", []))
        inspected = set(state.get("files_read", []))
        if current_path not in discovered:
            return deny(f"'{current_path}' was not discovered by search_code. Search for it first.")
        if current_path not in inspected and len(inspected) >= int(state.get("max_source_files", 4)):
            return deny("Source inspection budget exhausted.")
        if current_path in inspected:
            return deny(f"You already inspected '{current_path}'. Inspect a relevant symbol or another file instead.")
        normalized["path"] = str(normalized["path"])

    elif name == "read_symbol":
        file_path = normalized.get("file")
        symbol_name = str(normalized.get("symbol_name", "")).strip()
        if not file_path:
            return deny("read_symbol requires 'file'.")
        if not symbol_name:
            return deny("read_symbol requires 'symbol_name'.")
        try:
            current_path = _repo_relative_path(str(file_path), repo_path)
        except (OSError, ValueError) as exc:
            return deny(str(exc))
        discovered = set(state.get("files_seen_in_search", []))
        inspected = set(state.get("files_read", []))
        if current_path not in discovered:
            return deny(f"'{current_path}' was not discovered by search_code. Search for it first.")
        if current_path not in inspected and len(inspected) >= int(state.get("max_source_files", 4)):
            return deny("Source inspection budget exhausted.")
        symbol_key = f"{current_path}::{symbol_name}"
        if symbol_key in set(state.get("symbols_read", [])):
            return deny(f"You already inspected '{symbol_name}' in '{current_path}'. Choose another relevant symbol or file.")
        normalized["file"] = current_path
        normalized["root_path"] = repo_path

    elif name == "git_log":
        normalized["repo_path"] = repo_path

    return {
        "status": "tool_ready",
        "current_tool_name": name,
        "current_tool_arguments": normalized,
        "validated_tool_call": {"name": name, "arguments": normalized},
        "current_tool_repo_relative_path": current_path,
        "current_symbol_key": symbol_key,
    }


def _route_after_validation(state: AgentLoopState) -> str:
    return "execute_tool" if state.get("status") == "tool_ready" else "observe"


def _execute_tool(state: AgentLoopState, *, tools: ToolRegistry) -> dict[str, Any]:
    call = state.get("validated_tool_call") or {}
    name = str(call.get("name", ""))
    arguments = call.get("arguments", {})
    try:
        result = tools.execute(name, **arguments)
        succeeded = True
        paths: list[str] = []
        if name == "search_code" and hasattr(result, "paths"):
            paths = [str(path) for path in result.paths]
            formatted = _serialize_tool_result(result)
            all_paths = sorted(set(state.get("files_seen_in_search", [])) | set(paths))
            formatted += "\n\nAll discovered source files so far:\n" + "\n".join(all_paths)
        else:
            formatted = _serialize_tool_result(result)
        return {
            "status": "tool_ready",
            "current_tool_name": name,
            "current_tool_arguments": dict(arguments),
            "last_tool_result": formatted,
            "last_tool_succeeded": succeeded,
            "last_search_paths": paths,
        }
    except Exception as exc:
        error = f"Tool '{name}' failed: {exc}"
        return {
            "status": "tool_ready",
            "current_tool_name": name,
            "current_tool_arguments": dict(arguments),
            "last_tool_result": error,
            "last_tool_succeeded": False,
            "last_search_paths": [],
            "errors": [*state.get("errors", []), error],
        }


def _observe(state: AgentLoopState) -> dict[str, Any]:
    name = str(state.get("current_tool_name", ""))
    call = state.get("pending_tool_call") or {}
    if not name:
        name = str(call.get("name", "unknown"))
    result_text = str(state.get("last_tool_result", ""))
    succeeded = bool(state.get("last_tool_succeeded", False))
    
    messages = list(state.get("messages", []))

    tool_message: dict[str, Any] = {
        "role": "tool",
        "tool_name": name or "unknown",
        "content": result_text,
    }

    tool_call_id = call.get("id")

    if tool_call_id:
        tool_message["tool_call_id"] = tool_call_id
        tool_message["name"] = name or "unknown"

    messages.append(tool_message)

    print("\n========== TOOL OBSERVATION ==========")
    print(f"TOOL: {name}")
    print(f"SUCCESS: {succeeded}")
    print(f"RESULT: {result_text[:1500]}")
    print(f"INSPECTED BEFORE: {state.get('files_read', [])}")
    print("======================================\n")

    discovered = list(state.get("files_seen_in_search", []))
    for path in state.get("last_search_paths", []):
        try:
            normalized = _repo_relative_path(str(path), state.get("repo_path", ""))
        except (OSError, ValueError):
            normalized = str(path).replace("\\", "/")
        if normalized not in discovered:
            discovered.append(normalized)

    inspected = list(state.get("files_read", []))
    symbols = list(state.get("symbols_read", []))
    if succeeded and name in {"read_file", "read_symbol"}:
        current = state.get("current_tool_repo_relative_path", "")
        if current and current not in inspected:
            inspected.append(current)
        symbol_key = state.get("current_symbol_key", "")
        if name == "read_symbol" and symbol_key and symbol_key not in symbols:
            symbols.append(symbol_key)

    tool_calls = list(state.get("tool_calls", []))
    if succeeded:
        tool_calls.append(name)

    return {
        "status": "running",
        "messages": messages,
        "files_seen_in_search": discovered,
        "files_read": inspected,
        "symbols_read": symbols,
        "tool_calls": tool_calls,
        "pending_tool_call": None,
        "validated_tool_call": None,
        "current_tool_name": "",
        "current_tool_arguments": {},
        "current_tool_repo_relative_path": "",
        "current_symbol_key": "",
        "last_tool_result": "",
        "last_tool_succeeded": False,
        "last_search_paths": [],
    }


def build_agent_loop_graph(
    *,
    llm: BaseLLM,
    tools: ToolRegistry,
    policy: BasePolicy,
    max_steps: int = 5,
    max_search_calls: int = 3,
    max_source_files: int = 4,
    min_source_files: int = 2,
):
    """Compile the per-step investigation loop; LangGraph owns all routing."""
    builder = StateGraph(AgentLoopState)
    builder.add_node(
        "initialize",
        lambda state: _initialize(
            state,
            max_steps=max_steps,
            max_search_calls=max_search_calls,
            max_source_files=max_source_files,
            min_source_files=min_source_files,
        ),
    )
    builder.add_node("reason", lambda state: _reason(state, llm=llm, tools=tools))
    builder.add_node("validate_tool", lambda state: _validate_tool(state, policy=policy, tools=tools))
    builder.add_node("execute_tool", lambda state: _execute_tool(state, tools=tools))
    builder.add_node("observe", _observe)

    builder.add_edge(START, "initialize")
    builder.add_conditional_edges("initialize", _route_after_initialize, {"reason": "reason", END: END})
    builder.add_conditional_edges("reason", _route_after_reason, {"validate_tool": "validate_tool", "reason": "reason", END: END})
    builder.add_conditional_edges("validate_tool", _route_after_validation, {"execute_tool": "execute_tool", "observe": "observe"})
    builder.add_edge("execute_tool", "observe")
    builder.add_edge("observe", "reason")
    return builder.compile()


def run_agent_loop(
    *,
    query: str,
    repo_path: str,
    llm: BaseLLM,
    tools: ToolRegistry,
    policy: BasePolicy,
    max_steps: int = 5,
) -> AgentLoopState:
    graph = build_agent_loop_graph(llm=llm, tools=tools, policy=policy, max_steps=max_steps)
    return graph.invoke({"query": query, "repo_path": repo_path})
