from app.tools.code_index import build_index
from app.tools.search_code import SearchCodeTool


V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"


index = build_index(V2_REPO)

tool = SearchCodeTool(index=index)

result = tool.execute(
    query="redis",
    root_path=V2_REPO,
    top_k=5,
)

print(result)