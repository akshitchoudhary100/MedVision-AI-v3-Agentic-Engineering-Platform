import time
from app.llm.ollama_llm import OllamaLLM
from app.tools.git_log import GitLogTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool


V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"

MAX_STEPS = 5


def main() -> None:
    # ---------------------------------
    # 1. Create tool registry
    # ---------------------------------
    registry = ToolRegistry()

    registry.register(ReadFileTool())
    registry.register(SearchCodeTool())
    registry.register(GitLogTool())

    # ---------------------------------
    # 2. Create local LLM
    # ---------------------------------
    llm = OllamaLLM(model="qwen3:4b")

    # ---------------------------------
    # 3. Initial conversation
    # ---------------------------------
    messages = [
        {
            "role": "user",
            "content": (
                f"Investigate Redis usage in the repository {V2_REPO}. "
                "You must inspect relevant source files before giving "
                "your final answer. Start by searching for redis."
            ),
        }
    ]

    # ---------------------------------
    # 4. Agent loop
    # ---------------------------------
    agent_start = time.perf_counter()

    for step in range(1, MAX_STEPS + 1):

        print(f"\n{'=' * 60}")
        print(f"AGENT STEP {step}")
        print(f"{'=' * 60}")

        # -----------------------------
        # Measure LLM call
        # -----------------------------
        llm_start = time.perf_counter()

        response = llm.generate(
            messages=messages,
            tools=registry.definitions(),
        )

        llm_duration = time.perf_counter() - llm_start

        message = response.get("message", {})
        tool_calls = message.get("tool_calls", [])

        # -----------------------------
        # Ollama metrics
        # -----------------------------
        prompt_tokens = response.get("prompt_eval_count", 0)
        generated_tokens = response.get("eval_count", 0)

        eval_duration_ns = response.get("eval_duration", 0)

        if eval_duration_ns:
            tokens_per_second = (
                generated_tokens / (eval_duration_ns / 1_000_000_000)
            )
        else:
            tokens_per_second = 0

        print("\n=== LLM METRICS ===")
        print(f"LLM duration:      {llm_duration:.2f}s")
        print(f"Prompt tokens:     {prompt_tokens}")
        print(f"Generated tokens:  {generated_tokens}")
        print(f"Generation speed:  {tokens_per_second:.2f} tokens/sec")
        print(f"Tool calls:        {len(tool_calls)}")

        # -----------------------------
        # No tool call = final answer
        # -----------------------------
        if not tool_calls:

            print("\n=== FINAL ANSWER ===")
            print(message.get("content", ""))

            break

        # -----------------------------
        # Preserve assistant message
        # -----------------------------
        messages.append(message)

        # -----------------------------
        # Execute tools
        # -----------------------------
        for tool_call in tool_calls:

            function = tool_call["function"]

            tool_name = function["name"]
            arguments = function["arguments"]

            print("\n=== TOOL REQUEST ===")
            print(f"Tool: {tool_name}")
            print(f"Arguments: {arguments}")

            # -----------------------------
            # Measure tool execution
            # -----------------------------
            tool_start = time.perf_counter()

            tool_result = registry.execute(
                tool_name,
                **arguments,
            )

            tool_duration = time.perf_counter() - tool_start

            print(f"Tool duration: {tool_duration:.4f}s")

            # -----------------------------
            # Convert result to observation
            # -----------------------------
            if isinstance(tool_result, list):
                observation = "\n".join(tool_result)
            else:
                observation = str(tool_result)

            print("\n=== TOOL OBSERVATION ===")
            print(observation)

            # -----------------------------
            # Give observation to LLM
            # -----------------------------
            messages.append(
                {
                    "role": "tool",
                    "content": observation,
                }
            )

    else:
        print("\n=== MAXIMUM AGENT STEPS REACHED ===")
        print(f"The agent stopped after {MAX_STEPS} steps.")

    # ---------------------------------
    # Total agent duration
    # ---------------------------------
    total_agent_duration = time.perf_counter() - agent_start

    print("\n=== AGENT METRICS ===")
    print(f"Total agent duration: {total_agent_duration:.2f}s")
    print(f"Total steps attempted: {step}")

if __name__ == "__main__":
    main()