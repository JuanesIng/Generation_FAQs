import uuid
from typing import Dict, List

import numpy as np
from fastapi import FastAPI, HTTPException
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sentence_transformers import SentenceTransformer

from faq_common import DATA_DIR, load_json, load_json_lines, normalize_text, save_json
from faq_models import SuggestionResponse, SuggestionSummary

# Aplicacion FastAPI del servicio de sugerencias.
app = FastAPI(title="Everwod FAQ Suggestion Service")

# Mismo modelo usado para representar semanticamente las preguntas de usuarios.
MODEL_NAME = "all-MiniLM-L6-v2"

# Se carga en startup para reutilizarlo durante toda la vida del servicio.
EMBEDDING_MODEL: SentenceTransformer

# Archivos de entrada y salida del servicio.
SUGGESTIONS_PATH = DATA_DIR / "faq_suggestions.json"
CONVERSATIONS_PATH = DATA_DIR / "conversations.jsonl"


@app.on_event("startup")
def startup_event() -> None:
    """Carga el modelo de embeddings cuando arranca el servicio."""
    global EMBEDDING_MODEL
    EMBEDDING_MODEL = SentenceTransformer(MODEL_NAME)


def load_conversation_pairs() -> List[Dict[str, str]]:
    """Lee los pares usuario/asistente generados por el servicio de ingesta."""
    if not CONVERSATIONS_PATH.exists():
        raise FileNotFoundError(f"Conversation file not found: {CONVERSATIONS_PATH}")
    return load_json_lines(CONVERSATIONS_PATH)


def choose_cluster_count(total: int) -> int:
    """Escoge una cantidad razonable de clusters segun el volumen de ejemplos."""
    if total < 20:
        return max(2, total // 5)
    if total < 80:
        return 4
    if total < 200:
        return 8
    return min(12, max(4, total // 30))


def build_suggestions(conversations: List[Dict[str, str]]) -> SuggestionSummary:
    """Genera sugerencias de FAQ agrupando preguntas semanticamente similares."""
    if not conversations:
        raise ValueError("No conversation pairs available for suggestion generation.")

    # Usa solo el texto del usuario para detectar preguntas repetidas.
    user_texts = [normalize_text(item["user_text"]) for item in conversations]
    user_texts = [text for text in user_texts if text]
    if len(user_texts) < 4:
        raise ValueError("Insufficient user messages to generate FAQ suggestions.")

    # Convierte cada pregunta en un vector numerico comparable.
    embeddings = EMBEDDING_MODEL.encode(user_texts, convert_to_numpy=True, show_progress_bar=False)
    n_clusters = choose_cluster_count(len(user_texts))
    n_clusters = min(n_clusters, len(user_texts) - 1)

    # Agrupa preguntas parecidas con KMeans.
    model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = model.fit_predict(embeddings)
    cluster_centers = model.cluster_centers_

    suggestions: List[SuggestionResponse] = []
    cluster_groups: Dict[int, List[int]] = {}
    for index, label in enumerate(labels):
        cluster_groups.setdefault(int(label), []).append(index)

    # Para cada cluster, escoge la pregunta mas cercana al centro como representante.
    for label, indices in cluster_groups.items():
        center = cluster_centers[label]
        best_index = min(indices, key=lambda idx: np.linalg.norm(embeddings[idx] - center))
        question_text = user_texts[best_index]

        # Usa la respuesta historica mas repetida como respuesta sugerida.
        answers = [conversations[i]["assistant_text"] for i in indices if conversations[i].get("assistant_text")]
        answer_text = max(set(answers), key=answers.count) if answers else "Respuesta sugerida basada en el contexto de la conversación."

        # Guarda hasta tres ejemplos que ayuden al revisor humano a evaluar la sugerencia.
        examples = []
        for idx in indices[:3]:
            candidate = user_texts[idx]
            if candidate not in examples:
                examples.append(candidate)

        cluster_score = round(min(100.0, 100.0 * len(indices) / len(user_texts)), 2)
        suggestions.append(
            SuggestionResponse(
                id=str(uuid.uuid4()),
                question=question_text,
                answer=answer_text,
                cluster_size=len(indices),
                support_examples=examples,
                cluster_score=cluster_score,
            )
        )

    # La metrica silhouette solo aplica cuando hay mas de un cluster valido.
    silhouette = None
    if len(set(labels)) > 1 and len(user_texts) > len(set(labels)):
        silhouette = round(silhouette_score(embeddings, labels), 4)

    # Persiste el resumen para que otros endpoints o servicios puedan consultarlo.
    summary = SuggestionSummary(
        cluster_count=len(cluster_groups),
        total_examples=len(user_texts),
        average_cluster_size=round(len(user_texts) / len(cluster_groups), 2),
        silhouette_score=silhouette,
        suggestions=suggestions,
    )
    save_json(summary.dict(), SUGGESTIONS_PATH)
    return summary


@app.get("/health")
def health() -> dict:
    """Endpoint simple para confirmar que el servicio esta activo."""
    return {"status": "ok", "service": "suggestion", "model": MODEL_NAME}


@app.post("/suggest", response_model=SuggestionSummary)
def suggest() -> SuggestionSummary:
    """Endpoint principal: genera y guarda sugerencias nuevas."""
    conversations = load_conversation_pairs()
    return build_suggestions(conversations)


@app.get("/suggestions", response_model=SuggestionSummary)
def get_suggestions() -> SuggestionSummary:
    """Devuelve la ultima tanda de sugerencias generadas."""
    if not SUGGESTIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="No suggestions have been generated yet.")
    raw = load_json(SUGGESTIONS_PATH)
    return SuggestionSummary(**raw)


if __name__ == "__main__":
    import uvicorn

    # Levanta el servicio localmente en el puerto 8003.
    uvicorn.run("suggestion_service:app", host="127.0.0.1", port=8003, log_level="info")
