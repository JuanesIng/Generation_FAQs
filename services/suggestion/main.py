import asyncio
import json
import queue
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from faq_models import SuggestionSummary
from services.suggestion.generator import AnswerGenerator
from services.suggestion.pipeline import build_suggestions, load_conversation_pairs

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
def suggest(company_id: Optional[str] = None) -> SuggestionSummary:
    conversations = load_conversation_pairs(company_id)
    return build_suggestions(conversations, generator, company_id)



@app.get("/pipeline/stream")
async def pipeline_stream(company_id: Optional[str] = None):
    """Ejecuta el pipeline completo y transmite el progreso vía Server-Sent Events."""
    log_q: queue.Queue = queue.Queue()

    def run():
        try:
            log_q.put("Cargando conversaciones...")
            convs = load_conversation_pairs(company_id)
            log_q.put(f"  {len(convs)} pares cargados")
            log_q.put("Ejecutando clustering y generación de respuestas...")
            result = build_suggestions(convs, generator, company_id)
            log_q.put(f"  {result.company_count} empresas procesadas")
            log_q.put(f"  {result.cluster_count} sugerencias generadas")
            if result.avg_coherence_score is not None:
                log_q.put(f"  Coherencia: {result.avg_coherence_score:.3f}")
            if result.avg_answer_relevance is not None:
                log_q.put(f"  Relevancia respuesta: {result.avg_answer_relevance:.3f}")
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
                msg = await loop.run_in_executor(None, lambda: log_q.get(timeout=60))
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