from collections import defaultdict
from faq_common import load_json_lines, DATA_DIR, normalize_text
from services.suggestion.filters import is_good_faq_candidate
from services.suggestion.pipeline import company_key
import numpy as np

CONVERSATIONS_PATH = DATA_DIR / "conversations.jsonl"

# 1. Cuántos pares hay
conversations = load_json_lines(CONVERSATIONS_PATH)
print(f"\n Total pares cargados: {len(conversations)}")

# 2. Cuántos pasan el filtro
valid = [
    item for item in conversations
    if is_good_faq_candidate(normalize_text(item.get("user_text", "")))
]
print(f" Pasan is_good_faq_candidate: {len(valid)}")

# 3. Distribución por empresa
by_company = defaultdict(list)
for item in conversations:
    by_company[company_key(item)].append(item)

print(f" Empresas distintas: {len(by_company)}")
for cid, items in by_company.items():
    valid_count = sum(1 for i in items if is_good_faq_candidate(i.get("user_text", "")))
    print(f"   - {cid}: {len(items)} pares, {valid_count} válidos")

# 4. Muestra los primeros 5 user_texts que sí pasan
print("\n Ejemplos que pasan el filtro:")
for item in valid[:5]:
    print(f"   '{item['user_text']}'")

# 5. Muestra los primeros 5 que NO pasan
rejected = [
    item for item in conversations
    if not is_good_faq_candidate(normalize_text(item.get("user_text", "")))
]
print("\n Ejemplos rechazados:")
for item in rejected[:5]:
    print(f"   '{item['user_text']}'")

# 6. Si hay válidos, prueba el clustering
if len(valid) >= 3:
    from services.suggestion.generator import AnswerGenerator
    from services.suggestion.clustering import build_clusters, get_cluster_groups

    FAQ_CLUSTER_EPS = 0.34
    FAQ_MIN_CLUSTER_SIZE = 3

    generator = AnswerGenerator()
    generator.load()

    texts = [normalize_text(i["user_text"]) for i in valid[:100]]
    embeddings = generator.encode(texts)
    labels = build_clusters(embeddings, eps=FAQ_CLUSTER_EPS, min_samples=FAQ_MIN_CLUSTER_SIZE)

    noise = sum(1 for l in labels if l == -1)
    clusters = get_cluster_groups(labels)
    print(f"\n Clustering sobre {len(texts)} textos:")
    print(f"   Clusters encontrados: {len(clusters)}")
    print(f"   Puntos ruido (sin cluster): {noise}")

    for label, indices in list(clusters.items())[:3]:
        print(f"\n   Cluster {label} ({len(indices)} items):")
        for idx in indices[:3]:
            print(f"     '{texts[idx]}'")