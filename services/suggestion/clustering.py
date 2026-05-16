from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics import silhouette_score

from faq_common import normalize_text


def build_clusters(
    embeddings: np.ndarray,
    eps: float = 0.34,
    min_samples: int = 3,
) -> np.ndarray:
    model = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
    return model.fit_predict(embeddings)


def get_cluster_groups(labels: np.ndarray) -> Dict[int, List[int]]:
    groups: Dict[int, List[int]] = {}
    for index, label in enumerate(labels):
        if label != -1:
            groups.setdefault(int(label), []).append(index)
    return groups


def get_centroid_index(
    indices: List[int],
    embeddings: np.ndarray,
    texts: Optional[Sequence[str]] = None,
) -> int:
    center = np.mean(embeddings[indices], axis=0)
    center = center / np.linalg.norm(center)
    similarity = {idx: float(np.dot(embeddings[idx], center)) for idx in indices}

    if texts is not None:
        top3 = sorted(indices, key=lambda idx: similarity[idx], reverse=True)[:3]
        # Preferir candidatos con signo de pregunta
        with_question = [idx for idx in top3 if "?" in texts[idx]]
        if with_question:
            return max(with_question, key=lambda idx: similarity[idx])
        # Sin signo de pregunta: preferir el más corto entre los top-3
        return min(top3, key=lambda idx: len(texts[idx]))

    return max(indices, key=lambda idx: similarity[idx])


def compute_support(indices: List[int], embeddings: np.ndarray) -> float:
    center = np.mean(embeddings[indices], axis=0)
    center = center / np.linalg.norm(center)
    return round(float(np.mean([np.dot(embeddings[idx], center) for idx in indices])), 4)


def compute_silhouette(embeddings: np.ndarray, labels: np.ndarray) -> Optional[float]:
    clean_labels = [label for label in labels if label != -1]
    clean_embeddings = embeddings[labels != -1]
    if len(set(clean_labels)) > 1 and len(clean_embeddings) > len(set(clean_labels)):
        return round(silhouette_score(clean_embeddings, clean_labels, metric="cosine"), 4)
    return None