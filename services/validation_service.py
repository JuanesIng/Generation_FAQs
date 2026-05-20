from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from faq_common import DATA_DIR, company_data_dir, get_db_connection, load_json, save_json
from faq_models import (
    SuggestionEditRequest,
    ValidationRequest,
    ValidationResponse,
    ValidationStatus,
)

app = FastAPI(title="Everwod FAQ Validation Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_GLOBAL_SUGGESTIONS_PATH = DATA_DIR / "faq_suggestions.json"
_GLOBAL_VALIDATIONS_PATH = DATA_DIR / "faq_validations.json"


def _suggestions_path(company_id: Optional[str]):
    return (company_data_dir(company_id) / "suggestions.json") if company_id else _GLOBAL_SUGGESTIONS_PATH


def _validations_path(company_id: Optional[str]):
    return (company_data_dir(company_id) / "validations.json") if company_id else _GLOBAL_VALIDATIONS_PATH


def load_suggestions(company_id: Optional[str] = None) -> List[Dict[str, Any]]:
    path = _suggestions_path(company_id)
    if not path.exists():
        raise FileNotFoundError(f"No hay sugerencias para {'la empresa ' + company_id if company_id else 'ninguna empresa'}.")
    return load_json(path).get("suggestions", [])


def load_validations(company_id: Optional[str] = None) -> List[Dict[str, Any]]:
    path = _validations_path(company_id)
    if not path.exists() or path.stat().st_size == 0:
        return []
    return load_json(path)


def save_validations(validations: List[Dict[str, Any]], company_id: Optional[str] = None) -> None:
    save_json(validations, _validations_path(company_id))


def get_suggestion_by_id(suggestion_id: str, company_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return next((s for s in load_suggestions(company_id) if s["id"] == suggestion_id), None)


def get_validation_by_id(suggestion_id: str, company_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return next((v for v in load_validations(company_id) if v["suggestion_id"] == suggestion_id), None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "validation"}


@app.get("/suggestions")
def get_suggestions(company_id: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        return load_suggestions(company_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/suggestions/{suggestion_id}")
def get_suggestion(suggestion_id: str, company_id: Optional[str] = None) -> Dict[str, Any]:
    suggestion = get_suggestion_by_id(suggestion_id, company_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    return suggestion


@app.patch("/suggestions/{suggestion_id}")
def edit_suggestion(
    suggestion_id: str,
    body: SuggestionEditRequest,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    path = _suggestions_path(company_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No suggestions file found.")
    data = load_json(path)
    for s in data.get("suggestions", []):
        if s["id"] == suggestion_id:
            s["question"] = body.question
            s["answer"] = body.answer
            save_json(data, path)
            return s
    raise HTTPException(status_code=404, detail="Suggestion not found.")


@app.get("/validations")
def get_validations(company_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return load_validations(company_id)


@app.post("/validate", response_model=ValidationResponse)
def validate(request: ValidationRequest, company_id: Optional[str] = None) -> ValidationResponse:
    try:
        suggestions = load_suggestions(company_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not any(s["id"] == request.suggestion_id for s in suggestions):
        raise HTTPException(status_code=404, detail="Suggestion ID not found.")

    validations = load_validations(company_id)
    reviewed_at = request.reviewed_at or datetime.utcnow()
    entry = {
        "suggestion_id": request.suggestion_id,
        "reviewer": request.reviewer,
        "status": request.status,
        "notes": request.notes,
        "reviewed_at": reviewed_at.isoformat(),
    }
    validations.append(entry)
    save_validations(validations, company_id)
    return ValidationResponse(**entry)


@app.post("/promote/{suggestion_id}")
def promote(suggestion_id: str, company_id: Optional[str] = None) -> dict:
    validation = get_validation_by_id(suggestion_id, company_id)
    if not validation:
        raise HTTPException(status_code=404, detail="No validation found for this suggestion.")
    if validation["status"] != ValidationStatus.approved:
        raise HTTPException(status_code=400, detail="Suggestion is not approved.")

    suggestion = get_suggestion_by_id(suggestion_id, company_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found.")

    query = (
        "INSERT INTO agent_faqs (id, agent_id, question, answer, created_at) "
        "SELECT gen_random_uuid(), a.id, %s, %s, NOW() "
        "FROM agents a "
        "WHERE a.workspace_id::text = %s "
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


@app.get("/metrics/last")
def get_last_metrics() -> Dict[str, Any]:
    from metrics.cluster_metrics import load_all_metrics
    runs = load_all_metrics()
    if not runs:
        raise HTTPException(status_code=404, detail="No metrics available yet.")
    return runs[-1]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.validation_service:app", host="127.0.0.1", port=8004, log_level="info")
