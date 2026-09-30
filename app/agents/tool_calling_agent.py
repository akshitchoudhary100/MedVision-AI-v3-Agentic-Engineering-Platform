import re
from pathlib import Path
from typing import Any

from app.llm.base import BaseLLM
from app.policies.base import BasePolicy
from app.schemas.result import AgentResult, RiskLevel
from app.schemas.state import AgentState
from app.tools.registry import ToolRegistry
from app.agents.base import BaseAgent


class ToolCallingAgent(BaseAgent):
    """
    LLM-driven repository investigation agent.

    The LLM decides which tools/files to inspect.
    The runtime enforces investigation and evidence boundaries.

    Evidence grounding covers two ways a model can reference a file:
      1. A literal filename  -> "redis_cache.py"
      2. A dotted import path -> "app.cache.redis_cache" / "app.workers.tasks.run_prediction_task"
    Both are resolved to a basename and checked against files actually
    opened with read_file before a final answer is allowed to pass.
    """

    MIN_SOURCE_FILES = 2
    MAX_SOURCE_FILES = 3

    SOURCE_EXTENSIONS = {
        ".py",
    }

    # Matches:  from app.cache.redis_cache import ...
    #           import app.workers.tasks
    #           "app.workers.tasks.run_prediction_task"   (RQ-style string refs)
    _IMPORT_PATTERN = re.compile(
        r"(?:from|import)\s+([\w\.]+)"      # from/import statements
        r"|['\"]([\w]+(?:\.[\w]+){1,})['\"]"  # quoted dotted paths, e.g. RQ job strings
    )

    def __init__(
        self,
        llm: BaseLLM,
        tools: ToolRegistry,
        policy: BasePolicy,
        max_steps: int = 5,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.policy = policy
        self.max_steps = max_steps

    def _is_source_file(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.SOURCE_EXTENSIONS

    def _extract_referenced_files(self, text: str) -> set[str]:
        """
        Extract every literal .py filename mentioned in the final answer.
        """
        return set(re.findall(r"[\w./-]+\.py", text))

    def _extract_referenced_modules(self, text: str) -> set[str]:
        """
        Extract dotted Python module/import paths mentioned in the final
        answer (e.g. "app.cache.redis_cache", "app.workers.tasks.run_prediction_task")
        so they can be resolved to file basenames and checked as evidence.
        """
        modules: set[str] = set()
        for match in self._IMPORT_PATTERN.finditer(text):
            mod = match.group(1) or match.group(2)
            if mod and "." in mod:
                modules.add(mod)
        return modules

    def _module_to_basename(self, module: str) -> str:
        """
        app.cache.redis_cache -> redis_cache.py
        app.workers.tasks.run_prediction_task -> run_prediction_task.py

        Note: for a dotted path ending in a function name (not a module),
        this guesses wrong on purpose-safe side: it still won't match any
        real file basename, so it correctly stays "ungrounded" rather than
        silently passing. Refine later if this causes false positives on
        your repo's naming conventions.
        """
        return module.split(".")[-1] + ".py"

    def _validate_tool_permission(self, tool_name: str) -> None:
        if not self.policy.is_allowed(tool_name):
            raise PermissionError(
                f"Tool '{tool_name}' is not allowed by the agent policy."
            )

    def _run_loop(
        self,
        state: AgentState,
        messages: list[dict[str, Any]],
    ) -> AgentResult:
        """
        Run the investigation agent.

        Workflow:

            SEARCH
              |
            READ SOURCE FILES
              |
            MINIMUM EVIDENCE
              |
            FINAL ANSWER
              |
            EVIDENCE VALIDATION (filenames + dotted import paths)
              |
            AgentResult
        """

        stage = "discovery"
        files_seen_in_search: set[str] = set()
        files_read: set[str] = set()

        for step in range(1, self.max_steps + 1):

            print(f"\n{'=' * 60}")
            print(f"AGENT STEP {step}")
            print(f"CURRENT STAGE: {stage}")
            print(f"FILES READ: {len(files_read)}")
            print(f"{'=' * 60}")

            response = self.llm.generate(
                messages=messages,
                tools=self.tools.definitions(),
            )

            print("\n=== RAW LLM RESPONSE ===")
            print(response)

            message = response.get("message", {})
            tool_calls = message.get("tool_calls", [])

            # =========================================================
            # LLM DID NOT REQUEST A TOOL
            # =========================================================
            if not tool_calls:

                # -----------------------------------------------------
                # Premature final answer
                # -----------------------------------------------------
                if stage != "final":
                    print("\nLLM attempted to answer before minimum evidence was collected.")
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You are not allowed to finalize yet.\n\n"
                                f"You have inspected {len(files_read)} source files.\n"
                                f"At least {self.MIN_SOURCE_FILES} distinct source files are required.\n\n"
                                "Call read_file on another relevant source implementation file."
                            ),
                        }
                    )
                    continue

                # -----------------------------------------------------
                # Final answer stage
                # -----------------------------------------------------
                final_text = message.get("content", "").strip()

                if not final_text:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your final response was empty. Provide a concise "
                                "answer using only the evidence from the files you inspected."
                            ),
                        }
                    )
                    continue

                # =====================================================
                # EVIDENCE VALIDATION
                # =====================================================
                claimed_files = self._extract_referenced_files(final_text)
                claimed_modules = self._extract_referenced_modules(final_text)
                claimed_module_basenames = {
                    self._module_to_basename(m) for m in claimed_modules
                }

                read_basenames = {Path(path).name for path in files_read}
                claimed_basenames = {Path(path).name for path in claimed_files}

                all_claimed = claimed_basenames | claimed_module_basenames
                ungrounded_files = all_claimed - read_basenames

                # -----------------------------------------------------
                # Evidence validation failed
                # -----------------------------------------------------
                if ungrounded_files:
                    print("\n=== EVIDENCE VALIDATION FAILED ===")
                    print("Unread files/modules referenced:")
                    for path in sorted(ungrounded_files):
                        print(f"  - {path}")

                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your proposed final answer failed evidence validation.\n\n"
                                "You referenced these files or modules without actually "
                                "inspecting them (this includes import statements and "
                                "dotted module paths, not just filenames):\n"
                                f"{sorted(ungrounded_files)}\n\n"
                                "You actually inspected only:\n"
                                f"{sorted(read_basenames)}\n\n"
                                "Rewrite the answer using ONLY evidence from files you "
                                "actually inspected. Do not describe what an unread module "
                                "'probably' does based on its import or its function names.\n\n"
                                "If information about another file is required, call "
                                "read_file on that file first."
                            ),
                        }
                    )
                    continue

                # =====================================================
                # EVIDENCE VALIDATION PASSED
                # =====================================================
                print("\n=== EVIDENCE VALIDATION PASSED ===")
                print("\nFiles actually inspected:")
                for path in sorted(files_read):
                    print(f"  - {path}")

                state.observations.append("Files actually inspected:")
                state.observations.extend(sorted(files_read))
                state.findings.append(final_text)
                state.current_step = "Investigation completed with validated evidence"

                return AgentResult(
                    task_id=state.task.task_id,
                    success=True,
                    summary="Repository investigation completed with validated evidence.",
                    findings=[final_text],
                    evidence=sorted(files_read),
                    errors=[],
                    risk_level=RiskLevel.LOW,
                    requires_human_approval=True,
                )

            # =========================================================
            # LLM REQUESTED TOOLS
            # =========================================================
            messages.append(message)

            for tool_call in tool_calls:

                function = tool_call.get("function", {})
                tool_name = function.get("name")
                arguments = function.get("arguments", {})

                if not tool_name:
                    raise ValueError("LLM returned an empty tool name.")

                print(f"\nRequested tool: {tool_name}")
                print(f"Arguments: {arguments}")

                self._validate_tool_permission(tool_name)

                # =====================================================
                # GIT LOG
                # =====================================================
                if tool_name == "git_log":

                    if stage != "discovery":
                        raise RuntimeError("git_log is only allowed during the discovery stage.")

                    result = self.tools.execute(tool_name, **arguments)

                    if not isinstance(result, list):
                        raise TypeError("git_log must return a list of commits.")

                    observation = "Git history retrieved:\n\n" + "\n".join(result)
                    messages.append({"role": "tool", "content": observation})

                    state.tool_calls.append("git_log")
                    state.observations.append("Git history:\n" + "\n".join(result))
                    state.current_step = "Repository history inspected"
                    continue

                # =====================================================
                # SEARCH CODE
                # =====================================================
                if tool_name == "search_code":

                    if stage != "discovery":
                        raise RuntimeError("search_code is only allowed during the search stage.")

                    result = self.tools.execute(tool_name, **arguments)

                    if not isinstance(result, list):
                        raise TypeError("search_code must return a list of file paths.")

                    files_seen_in_search = set(result)
                    source_candidates = [p for p in result if self._is_source_file(p)]

                    print("\n=== SEARCH RESULTS ===")
                    print(f"Total files found: {len(result)}")
                    print(f"Source candidates: {len(source_candidates)}")
                    for path in source_candidates:
                        print(path)

                    if not source_candidates:
                        return AgentResult(
                            task_id=state.task.task_id,
                            success=False,
                            summary="Investigation failed because no source files were found.",
                            findings=[],
                            evidence=[],
                            errors=["Search returned no Python source files."],
                            risk_level=RiskLevel.LOW,
                            requires_human_approval=True,
                        )

                    observation = (
                        "Search completed.\n\n"
                        "The following Python source files are valid candidates for inspection:\n\n"
                        + "\n".join(source_candidates)
                    )
                    messages.append({"role": "tool", "content": observation})

                    stage = "reading_files"
                    state.current_step = "Reading relevant source files"
                    state.tool_calls.append("search_code")
                    continue

                # =====================================================
                # READ FILE
                # =====================================================
                elif tool_name == "read_file":

                    if stage not in {"reading_files", "final"}:
                        raise RuntimeError("read_file cannot be used during the current stage.")

                    path = arguments.get("path", "")
                    if not path:
                        raise ValueError("read_file requires a path.")

                    if not self._is_source_file(path):
                        raise PermissionError(
                            f"'{path}' is not an allowed source file. "
                            "Read a relevant .py implementation file."
                        )

                    if path not in files_seen_in_search:
                        raise PermissionError(
                            f"'{path}' was not returned by search_code. "
                            "You may only read files discovered during this investigation."
                        )

                    if path not in files_read and len(files_read) >= self.MAX_SOURCE_FILES:
                        raise RuntimeError(
                            f"Maximum of {self.MAX_SOURCE_FILES} source files may be inspected."
                        )

                    result = self.tools.execute(tool_name, **arguments)

                    files_read.add(path)
                    state.tool_calls.append("read_file")
                    state.observations.append(f"FILE: {path}\n{result}")

                    messages.append(
                        {
                            "role": "tool",
                            "content": f"FILE ACTUALLY INSPECTED: {path}\n\n{result}",
                        }
                    )

                    print("\n=== EVIDENCE STATE ===")
                    print(f"Files actually read: {len(files_read)}")
                    for file_path in sorted(files_read):
                        print(f"  - {file_path}")

                    if len(files_read) >= self.MIN_SOURCE_FILES:
                        stage = "final"
                        state.current_step = "Enough evidence collected; final answer allowed"
                    else:
                        stage = "reading_files"
                        state.current_step = "More source files must be inspected"
                    continue

                # =====================================================
                # UNKNOWN TOOL
                # =====================================================
                else:
                    raise ValueError(f"Tool '{tool_name}' is not handled by ToolCallingAgent.")

        # =============================================================
        # MAX STEPS REACHED
        # =============================================================
        return AgentResult(
            task_id=state.task.task_id,
            success=False,
            summary="Investigation stopped before a validated final answer was produced.",
            findings=[],
            evidence=sorted(files_read),
            errors=[f"Agent stopped after {self.max_steps} steps."],
            risk_level=RiskLevel.LOW,
            requires_human_approval=True,
        )

    def _execute(self, state: AgentState) -> AgentResult:

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a repository investigation agent.\n\n"
                    "Rules:\n"
                    "1. Use tools to inspect the repository.\n"
                    "2. Never guess repository facts.\n"
                    "3. Search the repository before inspecting files.\n"
                    "4. Inspect relevant Python source files.\n"
                    "5. Inspect at least two source files before answering.\n"
                    "6. Use only evidence from files you actually inspected.\n"
                    "7. Never describe what a file you have not read 'probably' "
                    "contains, including files only seen via import statements.\n"
                    "8. If evidence is insufficient, inspect another file.\n"
                    "9. Keep the final answer concise and evidence-based."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Investigate the following repository:\n"
                    f"{state.task.metadata.get('repo_path', '')}\n\n"
                    f"Investigation request:\n"
                    f"{state.task.description}"
                ),
            },
        ]

        return self._run_loop(state=state, messages=messages)