from app.tools.code_index import build_index
from app.tools.read_symbol import read_symbol


V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"

index = build_index(V2_REPO)

result = read_symbol(
    index=index,
    root_path=V2_REPO,
    file="app/cache/redis_cache.py",
    symbol_name="get_cached_prediction",
)

print(result)