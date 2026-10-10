from app.tools.code_index import build_index
from app.tools.read_symbol_tool import ReadSymbolTool


V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"


index = build_index(V2_REPO)

tool = ReadSymbolTool(index=index)

print(tool.definition())

print()

print(
    tool.execute(
        file="app/cache/redis_cache.py",
        symbol_name="get_cached_prediction",
        root_path=V2_REPO,
    )
)