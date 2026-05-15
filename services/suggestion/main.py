from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException

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


@app.get("/suggestions", response_model=SuggestionSummary)
def get_suggestions() -> SuggestionSummary:
    if not SUGGESTIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="No suggestions have been generated yet.")
    return SuggestionSummary(**load_json(SUGGESTIONS_PATH))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.suggestion.main:app", host="127.0.0.1", port=8003, log_level="info")