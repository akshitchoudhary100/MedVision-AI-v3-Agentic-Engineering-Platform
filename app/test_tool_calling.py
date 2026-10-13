from app.llm.ollama_llm import OllamaLLM
from app.tools.git_log import GitLogTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool


V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"


def main() -> None:
    # 1. Create registry
    registry = ToolRegistry()

    registry.register(ReadFileTool())
    registry.register(SearchCodeTool())
    registry.register(GitLogTool())

    # 2. Create LLM
    llm = OllamaLLM(
        model="qwen3:4b",
    )

    # 3. Ask the LLM to choose a tool
    messages = [
        {
            "role": "user",
            "content": (
                f"Search the repository {V2_REPO} "
                "for the word redis."
            ),
        }
    ]
    
    print("\n=== TOOL DEFINITIONS ===")

    for definition in registry.definitions():
        print(definition)


    response = llm.generate(
        messages=messages,
        tools=registry.definitions(),
    )

    print("\n=== RAW LLM RESPONSE ===")
    print(response)

    # 4. Inspect the model's tool call
    message = response.get("message", {})
    tool_calls = message.get("tool_calls", [])

    print("\n=== TOOL CALLS ===")

    if not tool_calls:
        print("No tool call generated.")
        return

    for tool_call in tool_calls:
        function = tool_call.get("function", {})

        tool_name = function.get("name")
        arguments = function.get("arguments", {})

        print(f"Tool: {tool_name}")
        print(f"Arguments: {arguments}")

        if not tool_name:
            raise ValueError("LLM returned an empty tool name.")

        result = registry.execute(
            tool_name,
            **arguments,
        )

        print("\n=== TOOL RESULT ===")
        print(f"Found {len(result)} matching files.")

        for file_path in result[:20]:
            print(file_path)


if __name__ == "__main__":
    main()