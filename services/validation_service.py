from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException

from faq_common import DATA_DIR, get_db_connection, load_json, save_json
from faq_models import ValidationRequest, ValidationResponse, ValidationStatus

app = FastAPI(title="Everwod FAQ Validation Service")

SUGGESTIONS_PATH = DATA_DIR / "faq_suggestions.json"
VALIDATIONS_PATH = DATA_DIR / "faq_validations.json"


def load_suggestions() -> List[Dict[str, Any]]:
    if not SUGGESTIONS_PATH.exists():
        raise FileNotFoundError("No FAQ suggestions available.")
    return load_json(SUGGESTIONS_PATH).get("suggestions", [])


def load_validations() -> List[Dict[str, Any]]:
    if VALIDATIONS_PATH.exists():
        return load_json(VALIDATIONS_PATH)
    return []


def save_validations(validations: List[Dict[str, Any]]) -> None:
    save_json(validations, VALIDATIONS_PATH)


def suggestion_exists(suggestion_id: str) -> bool:
    suggestions = load_suggestions()
    return any(item["id"] == suggestion_id for item in suggestions)


def get_suggestion_by_id(suggestion_id: str) -> Optional[Dict[str, Any]]:
    return next((s for s in load_suggestions() if s["id"] == suggestion_id), None)


def get_validation_by_id(suggestion_id: str) -> Optional[Dict[str, Any]]:
    return next((v for v in load_validations() if v["suggestion_id"] == suggestion_id), None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "validation"}


@app.get("/suggestions")
def get_suggestions() -> List[Dict[str, Any]]:
    return load_suggestions()


@app.get("/validations")
def get_validations() -> List[Dict[str, Any]]:
    return load_validations()


@app.post("/validate", response_model=ValidationResponse)
def validate(request: ValidationRequest) -> ValidationResponse:
    if not suggestion_exists(request.suggestion_id):
        raise HTTPException(status_code=404, detail="Suggestion ID not found.")

    validations = load_validations()
    reviewed_at = request.reviewed_at or datetime.utcnow()
    entry = {
        "suggestion_id": request.suggestion_id,
        "reviewer": request.reviewer,
        "status": request.status,
        "notes": request.notes,
        "reviewed_at": reviewed_at.isoformat(),
    }
    validations.append(entry)
    save_validations(validations)
    return ValidationResponse(**entry)


@app.post("/promote/{suggestion_id}")
def promote(suggestion_id: str) -> dict:
    validation = get_validation_by_id(suggestion_id)
    if not validation:
        raise HTTPException(status_code=404, detail="No validation found for this suggestion.")
    if validation["status"] != ValidationStatus.approved:
        raise HTTPException(status_code=400, detail="Suggestion is not approved.")

    suggestion = get_suggestion_by_id(suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found.")

    query = (
        "INSERT INTO agent_faqs (id, agent_id, question, answer, created_at) "
        "SELECT gen_random_uuid(), a.id, %s, %s, NOW() "
        "FROM agents a "
        "WHERE a.workspace_id = %s "
        "LIMIT 1"
    )

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (
                    suggestion["question"],
                    suggestion["answer"],
                    suggestion["company_id"],
                ))
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al promover: {exc}")

    return {"promoted": True, "suggestion_id": suggestion_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.validation_service:app", host="127.0.0.1", port=8004, log_level="info")