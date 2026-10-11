from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.orchestrator.langgraph_agent_loop import build_agent_loop_graph
from app.policies.agent_policy import AgentPolicy


@dataclass
class FakeSearchResult:
    paths: list[str]

    def as_text(self) -> str:
        return "Relevant files:\n" + "\n".join(self.paths)


class FakeRegistry:
    def __init__(self):
        self.executed: list[tuple[str, dict[str, Any]]] = []

    def definitions(self):
        return [
            {"type": "function", "function": {"name": "search_code", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "read_symbol", "parameters": {"type": "object"}}},
        ]

    def list_tools(self):
        return ["search_code", "read_file", "read_symbol"]

    def execute(self, name: str, **kwargs: Any):
        self.executed.append((name, dict(kwargs)))
        if name == "search_code":
            return FakeSearchResult(["src/a.py", "src/b.py"])
        if name == "read_file":
            return "source from a.py"
        if name == "read_symbol":
            return "def target(): pass"
        raise AssertionError(f"Unexpected tool: {name}")


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.messages_seen: list[list[dict[str, Any]]] = []

    def generate(self, messages, tools=None):
        self.calls += 1
        self.messages_seen.append(messages)
        return self.responses.pop(0)


def call(name: str, arguments: dict[str, Any]):
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        }
    }


def final(text: str):
    return {"message": {"role": "assistant", "content": text}}


def test_langgraph_owns_reason_validate_execute_observe_loop():
    repo = "/tmp/test-repo"
    llm = FakeLLM([
        call("search_code", {"query": "cache lookup"}),
        call("read_file", {"path": "src/a.py"}),
        call("read_symbol", {"file": "src/b.py", "symbol_name": "target"}),
        final("The target function is defined in src/b.py and the related source is in src/a.py."),
    ])
    tools = FakeRegistry()
    graph = build_agent_loop_graph(
        llm=llm,
        tools=tools,
        policy=AgentPolicy({"search_code", "read_file", "read_symbol"}),
        max_steps=6,
    )

    result = graph.invoke({"query": "Find the target function", "repo_path": repo})

    assert result["status"] == "completed"
    assert result["summary"].startswith("The target function")
    assert result["evidence"] == ["src/a.py", "src/b.py"]
    assert [name for name, _ in tools.executed] == ["search_code", "read_file", "read_symbol"]
    assert llm.calls == 4
    # The model sees tool observations on subsequent reasoning passes.
    assert any(message.get("role") == "tool" for message in llm.messages_seen[-1])
    assert all("src/a.py" in kwargs.get("path", "") or name != "read_file" for name, kwargs in tools.executed)


def test_policy_denied_tool_is_never_executed_and_agent_can_continue():
    repo = "/tmp/test-repo"
    llm = FakeLLM([
        call("shell_command", {"command": "rm -rf ."}),
        call("search_code", {"query": "safe lookup"}),
        call("read_file", {"path": "src/a.py"}),
        call("read_symbol", {"file": "src/b.py", "symbol_name": "target"}),
        final("Evidence-based answer."),
    ])
    tools = FakeRegistry()
    graph = build_agent_loop_graph(
        llm=llm,
        tools=tools,
        policy=AgentPolicy({"search_code", "read_file", "read_symbol"}),
        max_steps=7,
    )

    result = graph.invoke({"query": "Investigate safely", "repo_path": repo})

    assert result["status"] == "completed"
    assert all(name != "shell_command" for name, _ in tools.executed)
    assert any("not allowed by policy" in message.get("content", "") for message in result["messages"] if message.get("role") == "tool")


def test_final_answer_is_rejected_until_minimum_source_evidence_exists():
    repo = "/tmp/test-repo"
    llm = FakeLLM([
        final("Unsupported initial claim."),
        call("search_code", {"query": "related source"}),
        call("read_file", {"path": "src/a.py"}),
        call("read_symbol", {"file": "src/b.py", "symbol_name": "target"}),
        final("Now the answer is grounded in both inspected source files."),
    ])
    tools = FakeRegistry()
    graph = build_agent_loop_graph(
        llm=llm,
        tools=tools,
        policy=AgentPolicy({"search_code", "read_file", "read_symbol"}),
        max_steps=7,
    )

    result = graph.invoke({"query": "Investigate source", "repo_path": repo})

    assert result["status"] == "completed"
    assert result["summary"].startswith("Now the answer")
    assert llm.calls == 5
