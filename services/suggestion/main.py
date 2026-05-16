import asyncio
import json
import queue
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from faq_common import DATA_DIR, load_json
from faq_models import SuggestionSummary
from services.suggestion.generator import AnswerGenerator
from services.suggestion.pipeline import build_suggestions, load_conversation_pairs

SUGGESTIONS_PATH = DATA_DIR / "faq_suggestions.json"

generator = AnswerGenerator()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    generator.load()
    yield


app = FastAPI(title="Everwod FAQ Suggestion Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "suggestion",
        "embedding_model": generator.embedding_model_name,
        "answer_model": generator.llm_model_name,
    }


@app.post("/suggest", response_model=SuggestionSummary)
def suggest() -> SuggestionSummary:
    conversations = load_conversation_pairs()
    return build_suggestions(conversations, generator)



@app.get("/pipeline/stream")
async def pipeline_stream():
    """Ejecuta el pipeline completo y transmite el progreso vía Server-Sent Events."""
    log_q: queue.Queue = queue.Queue()

    def run():
        try:
            log_q.put("Cargando conversaciones...")
            convs = load_conversation_pairs()
            log_q.put(f"  {len(convs)} pares cargados")
            log_q.put("Ejecutando clustering y generación de respuestas...")
            result = build_suggestions(convs, generator)
            log_q.put(f"  {result.company_count} empresas procesadas")
            log_q.put(f"  {result.cluster_count} sugerencias generadas")
            if result.silhouette_score is not None:
                log_q.put(f"  Silhouette score: {result.silhouette_score:.3f}")
            log_q.put("Pipeline completado.")
        except Exception as exc:
            log_q.put(f"Error: {exc}")
        finally:
            log_q.put(None)

    threading.Thread(target=run, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_event_loop()
        while True:
            try:
                msg = await loop.run_in_executor(None, lambda: log_q.get(timeout=3))
            except queue.Empty:
                yield f"data: {json.dumps({'step': 'Procesando...'})}\n\n"
                continue
            if msg is None:
                yield f"data: {json.dumps({'done': True})}\n\n"
                break
            yield f"data: {json.dumps({'step': msg})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.suggestion.main:app", host="127.0.0.1", port=8003, log_level="info")