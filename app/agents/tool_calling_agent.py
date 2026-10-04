from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.llm.base import BaseLLM
from app.policies.base import BasePolicy
from app.schemas.result import AgentResult
from app.schemas.state import AgentState
from app.tools.registry import ToolRegistry


class ToolCallingAgent:
    """
    LLM-driven investigation agent.

    The LLM decides:
        - when to search
        - when to inspect a file
        - when to inspect a symbol
        - when it has enough evidence to answer

    The runtime decides:
        - which tools are allowed
        - how many steps are allowed
        - how many searches are allowed
        - how many source files can be inspected
        - whether duplicate searches are allowed
        - whether the final answer has enough evidence

    The runtime does NOT hardcode an investigation sequence.
    """

    MIN_SOURCE_FILES = 2
    MAX_SOURCE_FILES = 4
    MAX_SEARCH_CALLS = 3

    def __init__(
        self,
        llm: BaseLLM,
        tools: ToolRegistry,
        policy: BasePolicy,
        max_steps: int = 10,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.policy = policy
        self.max_steps = max_steps

    # ================================================================
    # PATH HELPERS
    # ================================================================

    def _normalize_repo_path(
        self,
        path: str,
        repo_path: str,
    ) -> str:
        """
        Convert a path into repository-relative form.
        """

        repo = Path(repo_path).resolve()
        candidate = Path(path).expanduser()

        if not candidate.is_absolute():
            return candidate.as_posix()

        try:
            return candidate.resolve().relative_to(repo).as_posix()
        except ValueError:
            return candidate.as_posix()

    def _absolute_repo_path(
        self,
        path: str,
        repo_path: str,
    ) -> str:
        """
        Convert a repository-relative path into an absolute path.
        """

        candidate = Path(path).expanduser()

        if candidate.is_absolute():
            return candidate.as_posix()

        return (
            Path(repo_path) / candidate
        ).resolve().as_posix()

    # ================================================================
    # QUERY HELPERS
    # ================================================================

    @staticmethod
    def _normalize_query(query: str) -> str:
        """
        Normalize a search query.

        Example:

            " Redis "
            "redis"

        become:

            "redis"
        """

        return " ".join(
            query.lower().strip().split()
        )

    # ================================================================
    # SYSTEM PROMPT
    # ================================================================

    def _system_prompt(
        self,
        state: AgentState,
    ) -> str:

        repo_path = state.task.metadata.get(
            "repo_path",
            "",
        )

        return f"""
You are a software repository investigation agent.

Your task is:

{state.task.description}

Repository:

{repo_path}


AVAILABLE TOOLS
---------------

search_code
read_symbol
read_file
git_log


INVESTIGATION STRATEGY
----------------------

Start with search_code to discover relevant source files.

After discovering relevant files:

1. If one specific function or class is relevant:
   prefer read_symbol.

2. If broader file-level context is required:
   use read_file.

3. After inspecting source code, decide whether you have enough
   evidence to answer.

4. If evidence is insufficient:
   investigate another specific file, function, class, caller,
   configuration, import, or related concept.

5. You may perform multiple searches when necessary.


SEARCH RULES
------------

Never repeat the exact same search query.

If the first search is insufficient, make the next query more
specific using something learned from the inspected source.

Example:

First:
    redis

Then:
    get_cached_prediction

Then:
    redis_sync

Do NOT repeatedly search:

    redis


READ_SYMBOL RULE
----------------

Use read_symbol when you know the specific function or class
you want to inspect.

Example:

    get_cached_prediction
    RedisCache
    set_cached_prediction

Use read_file when you need broader file context.


EVIDENCE RULE
-------------

A file appearing in search results is NOT evidence.

Search results only tell you which files may be relevant.

A file becomes evidence only after:

    read_file

or:

    read_symbol


FINAL ANSWER RULE
-----------------

Your final answer must be based on source code that you actually
inspected.

Do not invent:

- functions
- classes
- variables
- files
- endpoints
- workflows
- configuration
- implementation details

Do not claim that a file was inspected merely because search_code
returned it.

If you need information from another file, inspect that file first.


INVESTIGATION BUDGET
--------------------

Maximum search calls:
{self.MAX_SEARCH_CALLS}

Maximum distinct source files inspected:
{self.MAX_SOURCE_FILES}

Minimum distinct source files required:
{self.MIN_SOURCE_FILES}

Maximum agent steps:
{self.max_steps}


IMPORTANT
---------

The runtime controls budgets and policy.

You control the investigation strategy.

Do not assume that the runtime wants a particular fixed sequence.

Choose the next useful investigation action yourself.
"""

    # ================================================================
    # MESSAGE BUILDING
    # ================================================================

    def _build_messages(
        self,
        state: AgentState,
        conversation: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        return [
            {
                "role": "system",
                "content": self._system_prompt(state),
            },
            {
                "role": "user",
                "content": state.task.description,
            },
            *conversation,
        ]

    # ================================================================
    # FINAL ANSWER VALIDATION
    # ================================================================

    def _validate_final_answer(
        self,
        files_read: set[str],
    ) -> None:
        """
        Require real source evidence before accepting
        a final answer.
        """

        if len(files_read) < self.MIN_SOURCE_FILES:
            raise RuntimeError(
                "Final answer rejected: insufficient source evidence. "
                f"Inspected {len(files_read)} distinct source file(s), "
                f"but at least {self.MIN_SOURCE_FILES} are required."
            )

    # ================================================================
    # TOOL ARGUMENT NORMALIZATION
    # ================================================================

    def _normalize_tool_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        repo_path: str,
    ) -> dict[str, Any]:

        normalized = dict(arguments)

        if tool_name in {
            "read_file",
            "read_symbol",
        }:

            if "file" in normalized:
                normalized["file"] = (
                    self._normalize_repo_path(
                        normalized["file"],
                        repo_path,
                    )
                )

            if "path" in normalized:
                normalized["path"] = (
                    self._absolute_repo_path(
                        normalized["path"],
                        repo_path,
                    )
                )

        if tool_name in {
            "search_code",
            "read_symbol",
        }:

            normalized["root_path"] = repo_path

        return normalized

    # ================================================================
    # TOOL RESULT SERIALIZATION
    # ================================================================

    @staticmethod
    def _serialize_tool_result(
        result: Any,
    ) -> str:

        if isinstance(result, str):
            return result

        if hasattr(result, "as_text"):
            return result.as_text()

        try:
            return json.dumps(
                result,
                indent=2,
                default=str,
            )
        except TypeError:
            return str(result)

    # ================================================================
    # OLLAMA RESPONSE PARSER
    # ================================================================

    def _parse_llm_response(
        self,
        raw_response: dict[str, Any],
    ) -> dict[str, Any]:

        message = raw_response.get(
            "message",
            {},
        )

        if not isinstance(message, dict):
            raise ValueError(
                "Invalid Ollama response: "
                "'message' must be an object."
            )

        tool_calls = message.get(
            "tool_calls",
            [],
        )

        if tool_calls:

            tool_call = tool_calls[0]

            function = tool_call.get(
                "function",
                {},
            )

            if not isinstance(function, dict):
                raise ValueError(
                    "Invalid Ollama tool call."
                )

            name = function.get("name")

            arguments = function.get(
                "arguments",
                {},
            )

            if not name:
                raise ValueError(
                    "Ollama returned a tool call "
                    "without a function name."
                )

            if not isinstance(arguments, dict):
                raise ValueError(
                    f"Invalid arguments for tool "
                    f"'{name}'. Expected an object."
                )

            return {
                "type": "tool_call",
                "name": name,
                "arguments": arguments,
                "message": message,
            }

        return {
            "type": "final",
            "content": message.get(
                "content",
                "",
            ),
            "message": message,
        }

    # ================================================================
    # APPEND ASSISTANT TOOL CALL
    # ================================================================

    @staticmethod
    def _append_assistant_message(
        conversation: list[dict[str, Any]],
        message: dict[str, Any],
    ) -> None:
        """
        Preserve the assistant's complete Ollama message.

        This is important for multi-step tool calling.
        """

        assistant_message = {
            "role": "assistant",
            "content": message.get(
                "content",
                "",
            ),
        }

        if message.get("tool_calls"):
            assistant_message["tool_calls"] = (
                message["tool_calls"]
            )

        if message.get("thinking"):
            assistant_message["thinking"] = (
                message["thinking"]
            )

        conversation.append(
            assistant_message
        )

    # ================================================================
    # APPEND TOOL RESULT
    # ================================================================

    @staticmethod
    def _append_tool_result(
        conversation: list[dict[str, Any]],
        tool_name: str,
        result: str,
    ) -> None:
        """
        Append the tool result using Ollama's expected
        tool-message format.
        """

        conversation.append(
            {
                "role": "tool",
                "tool_name": tool_name,
                "content": result,
            }
        )

    # ================================================================
    # MAIN LOOP
    # ================================================================

    def run(
        self,
        state: AgentState,
    ) -> AgentResult:

        state.status = "running"

        repo_path = state.task.metadata.get(
            "repo_path"
        )

        if not repo_path:

            state.status = "failed"

            error = (
                "Repository path is missing "
                "from task metadata."
            )

            state.errors.append(error)

            return AgentResult(
                task_id=state.task.task_id,
                success=False,
                errors=[error],
            )

        # ------------------------------------------------------------
        # Investigation memory
        # ------------------------------------------------------------

        files_seen_in_search: set[str] = set()

        files_read: set[str] = set()

        queries_used: set[str] = set()

        symbols_read: set[
            tuple[str, str]
        ] = set()

        search_count = 0

        conversation: list[
            dict[str, Any]
        ] = []

        # ------------------------------------------------------------
        # Agent loop
        # ------------------------------------------------------------

        for step in range(
            1,
            self.max_steps + 1,
        ):

            state.current_step = (
                f"tool_calling_step_{step}"
            )

            # ========================================================
            # CALL LLM
            # ========================================================

            try:

                raw_response = self.llm.generate(
                    messages=self._build_messages(
                        state,
                        conversation,
                    ),
                    tools=self.tools.definitions(),
                )

                response = (
                    self._parse_llm_response(
                        raw_response
                    )
                )

            except Exception as exc:

                state.status = "failed"

                error = str(exc)

                state.errors.append(error)

                return AgentResult(
                    task_id=state.task.task_id,
                    success=False,
                    errors=[error],
                )

            # ========================================================
            # FINAL ANSWER
            # ========================================================

            if response["type"] == "final":

                answer = (
                    response.get(
                        "content",
                        "",
                    )
                    .strip()
                )

                # Empty answer is not valid.
                if not answer:

                    conversation.append(
                        {
                            "role": "user",
                            "content": (
                                "Your answer was empty. "
                                "Continue the investigation "
                                "or provide the evidence-based "
                                "final answer."
                            ),
                        }
                    )

                    continue

                # Hard evidence requirement.
                try:

                    self._validate_final_answer(
                        files_read
                    )

                except RuntimeError as exc:

                    conversation.append(
                        {
                            "role": "assistant",
                            "content": answer,
                        }
                    )

                    conversation.append(
                        {
                            "role": "user",
                            "content": (
                                f"{exc}\n\n"
                                "Do not answer yet.\n"
                                "Continue investigating using "
                                "search_code, read_symbol, "
                                "or read_file."
                            ),
                        }
                    )

                    continue

                # ----------------------------------------------------
                # Success
                # ----------------------------------------------------

                state.status = "completed"
                state.workflow_state = "completed"

                return AgentResult(
                    task_id=state.task.task_id,
                    success=True,
                    summary=answer,
                    findings=list(
                        state.findings
                    ),
                    evidence=sorted(
                        files_read
                    ),
                    errors=list(
                        state.errors
                    ),
                )

            # ========================================================
            # EXPECT TOOL CALL
            # ========================================================

            if response["type"] != "tool_call":

                error = (
                    "Unsupported LLM response type: "
                    f"{response.get('type')}"
                )

                state.status = "failed"

                state.errors.append(error)

                return AgentResult(
                    task_id=state.task.task_id,
                    success=False,
                    errors=[error],
                )

            tool_name = response.get(
                "name"
            )

            arguments = response.get(
                "arguments",
                {},
            )

            if not tool_name:

                error = (
                    "LLM returned a tool call "
                    "without a tool name."
                )

                state.status = "failed"

                state.errors.append(error)

                return AgentResult(
                    task_id=state.task.task_id,
                    success=False,
                    errors=[error],
                )

            if not isinstance(
                arguments,
                dict,
            ):

                error = (
                    f"Invalid arguments for "
                    f"'{tool_name}'."
                )

                state.status = "failed"

                state.errors.append(error)

                return AgentResult(
                    task_id=state.task.task_id,
                    success=False,
                    errors=[error],
                )

            # --------------------------------------------------------
            # Preserve assistant tool-call message.
            # --------------------------------------------------------

            self._append_assistant_message(
                conversation,
                response["message"],
            )

            # ========================================================
            # POLICY
            # ========================================================

            if not self.policy.is_allowed(
                tool_name
            ):

                error = (
                    f"Tool '{tool_name}' "
                    "is not allowed by policy."
                )

                state.errors.append(error)

                self._append_tool_result(
                    conversation,
                    tool_name,
                    error,
                )

                continue

            # ========================================================
            # SEARCH CODE
            # ========================================================

            if tool_name == "search_code":

                if search_count >= (
                    self.MAX_SEARCH_CALLS
                ):

                    message = (
                        "Search budget exhausted. "
                        "Use the already discovered files "
                        "or inspect a specific symbol."
                    )

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        message,
                    )

                    continue

                query = str(
                    arguments.get(
                        "query",
                        "",
                    )
                ).strip()

                if not query:

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        "Search query cannot be empty.",
                    )

                    continue

                normalized_query = (
                    self._normalize_query(
                        query
                    )
                )

                if normalized_query in queries_used:

                    message = (
                        f"You already searched for "
                        f"'{query}'. "
                        "Use a more specific query "
                        "based on evidence learned."
                    )

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        message,
                    )

                    continue

                queries_used.add(
                    normalized_query
                )

                search_count += 1

                normalized_arguments = (
                    self._normalize_tool_arguments(
                        tool_name,
                        arguments,
                        repo_path,
                    )
                )

                try:

                    result = self.tools.execute(
                        tool_name,
                        **normalized_arguments,
                    )

                except Exception as exc:

                    error = (
                        f"Tool '{tool_name}' failed: "
                        f"{exc}"
                    )

                    state.errors.append(
                        error
                    )

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        error,
                    )

                    continue

                # ----------------------------------------------------
                # Accumulate discovered files.
                # ----------------------------------------------------

                if hasattr(
                    result,
                    "paths",
                ):

                    new_paths = {
                        self._normalize_repo_path(
                            path,
                            repo_path,
                        )
                        for path in result.paths
                    }

                    files_seen_in_search.update(
                        new_paths
                    )

                    formatted_result = (
                        result.as_text()
                    )

                    formatted_result += (
                        "\n\n"
                        "All discovered source files so far:\n"
                        + "\n".join(
                            sorted(
                                files_seen_in_search
                            )
                        )
                    )

                else:

                    formatted_result = (
                        self._serialize_tool_result(
                            result
                        )
                    )

                state.tool_calls.append(
                    tool_name
                )

                self._append_tool_result(
                    conversation,
                    tool_name,
                    formatted_result,
                )

                continue

            # ========================================================
            # READ FILE
            # ========================================================

            if tool_name == "read_file":

                path = arguments.get(
                    "path"
                )

                if not path:

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        "read_file requires 'path'.",
                    )

                    continue

                normalized_path = (
                    self._normalize_repo_path(
                        str(path),
                        repo_path,
                    )
                )

                # File must have been discovered.
                if (
                    normalized_path
                    not in files_seen_in_search
                ):

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        (
                            f"'{normalized_path}' "
                            "was not discovered by "
                            "search_code. Search for it first."
                        ),
                    )

                    continue

                # Distinct-file budget.
                if (
                    normalized_path
                    not in files_read
                    and len(files_read)
                    >= self.MAX_SOURCE_FILES
                ):

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        (
                            "Source inspection budget exhausted."
                        ),
                    )

                    continue

                # Avoid wasting a step rereading.
                if normalized_path in files_read:

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        (
                            f"You already inspected "
                            f"'{normalized_path}'. "
                            "Inspect a relevant symbol "
                            "or another file instead."
                        ),
                    )

                    continue

                normalized_arguments = (
                    self._normalize_tool_arguments(
                        tool_name,
                        arguments,
                        repo_path,
                    )
                )

                try:

                    result = self.tools.execute(
                        tool_name,
                        **normalized_arguments,
                    )

                except Exception as exc:

                    error = (
                        f"Tool '{tool_name}' failed: "
                        f"{exc}"
                    )

                    state.errors.append(
                        error
                    )

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        error,
                    )

                    continue

                files_read.add(
                    normalized_path
                )

                state.tool_calls.append(
                    tool_name
                )

                serialized_result = (
                    self._serialize_tool_result(
                        result
                    )
                )

                self._append_tool_result(
                    conversation,
                    tool_name,
                    serialized_result,
                )

                continue

            # ========================================================
            # READ SYMBOL
            # ========================================================

            if tool_name == "read_symbol":

                file = arguments.get(
                    "file"
                )

                symbol_name = arguments.get(
                    "symbol_name"
                )

                if not file:

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        (
                            "read_symbol requires 'file'."
                        ),
                    )

                    continue

                if not symbol_name:

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        (
                            "read_symbol requires "
                            "'symbol_name'."
                        ),
                    )

                    continue

                normalized_file = (
                    self._normalize_repo_path(
                        str(file),
                        repo_path,
                    )
                )

                # File must have been discovered.
                if (
                    normalized_file
                    not in files_seen_in_search
                ):

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        (
                            f"'{normalized_file}' "
                            "was not discovered by "
                            "search_code. Search for it first."
                        ),
                    )

                    continue

                # Distinct-file budget.
                if (
                    normalized_file
                    not in files_read
                    and len(files_read)
                    >= self.MAX_SOURCE_FILES
                ):

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        (
                            "Source inspection budget exhausted."
                        ),
                    )

                    continue

                symbol_key = (
                    normalized_file,
                    str(symbol_name),
                )

                # Avoid repeating exact symbol inspection.
                if symbol_key in symbols_read:

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        (
                            f"You already inspected "
                            f"'{symbol_name}' in "
                            f"'{normalized_file}'. "
                            "Choose another relevant "
                            "symbol or file."
                        ),
                    )

                    continue

                normalized_arguments = (
                    self._normalize_tool_arguments(
                        tool_name,
                        arguments,
                        repo_path,
                    )
                )

                try:

                    result = self.tools.execute(
                        tool_name,
                        **normalized_arguments,
                    )

                except Exception as exc:

                    error = (
                        f"Tool '{tool_name}' failed: "
                        f"{exc}"
                    )

                    state.errors.append(
                        error
                    )

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        error,
                    )

                    continue

                symbols_read.add(
                    symbol_key
                )

                files_read.add(
                    normalized_file
                )

                state.tool_calls.append(
                    tool_name
                )

                serialized_result = (
                    self._serialize_tool_result(
                        result
                    )
                )

                self._append_tool_result(
                    conversation,
                    tool_name,
                    serialized_result,
                )

                continue

            # ========================================================
            # GIT LOG
            # ========================================================

            if tool_name == "git_log":

                normalized_arguments = dict(
                    arguments
                )

                normalized_arguments[
                    "repo_path"
                ] = repo_path

                try:

                    result = self.tools.execute(
                        tool_name,
                        **normalized_arguments,
                    )

                except Exception as exc:

                    error = (
                        f"Tool '{tool_name}' failed: "
                        f"{exc}"
                    )

                    state.errors.append(
                        error
                    )

                    self._append_tool_result(
                        conversation,
                        tool_name,
                        error,
                    )

                    continue

                state.tool_calls.append(
                    tool_name
                )

                serialized_result = (
                    self._serialize_tool_result(
                        result
                    )
                )

                self._append_tool_result(
                    conversation,
                    tool_name,
                    serialized_result,
                )

                continue

            # ========================================================
            # UNKNOWN TOOL
            # ========================================================

            self._append_tool_result(
                conversation,
                tool_name,
                (
                    f"Unknown tool '{tool_name}'. "
                    f"Available tools: "
                    f"{self.tools.list_tools()}"
                ),
            )

        # ============================================================
        # STEP BUDGET EXHAUSTED
        # ============================================================

        error = (
            "Agent stopped after reaching the maximum "
            f"step budget ({self.max_steps}) without "
            "producing a valid final answer."
        )

        state.status = "failed"

        state.errors.append(
            error
        )

        return AgentResult(
            task_id=state.task.task_id,
            success=False,
            findings=list(
                state.findings
            ),
            evidence=sorted(
                files_read
            ),
            errors=list(
                state.errors
            ),
        )