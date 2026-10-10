from app.tools.code_index import build_index
from app.tools.search_code_ranked import rank_files, format_for_llm

V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"

index = build_index(V2_REPO)

ranked = rank_files(
    index=index,
    query="redis",
    root_path=V2_REPO,
    top_k=10,
)

print(format_for_llm(ranked))