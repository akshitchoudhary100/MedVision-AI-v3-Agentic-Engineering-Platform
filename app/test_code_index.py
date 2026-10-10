from app.tools.code_index import build_index

V2_REPO = "/Users/akshitchoudhary/MedVision-AI-v2.0-Production-AI-Inference-Platform"

index = build_index(V2_REPO)

print("Files indexed:", len(index.import_graph))
print("Symbols indexed:", len(index.symbol_table))

print("\nRedis-related symbols:")
for name in index.symbol_table:
    if "redis" in name.lower() or "cache" in name.lower():
        print(name, index.symbol_defining_file(name))