from datetime import datetime, timedelta
from collections import defaultdict
from typing import List

from fastapi import FastAPI

from faq_common import DATA_DIR, get_db_connection, json_text, normalize_text, save_json_lines
from faq_models import IngestRequest, IngestResponse

# Aplicacion FastAPI del servicio de ingesta.
app = FastAPI(title="Everwod FAQ Ingestion Service")

# Archivo intermedio que usaran los servicios siguientes.
OUTPUT_PATH = DATA_DIR / "conversations.jsonl"


def extract_text_from_message(payload) -> str:
    """Extrae el texto util desde el JSON de un mensaje de chat."""
    if not payload:
        return ""
    return normalize_text(json_text(payload.get("content") if isinstance(payload, dict) else payload))


def fetch_conversation_records(limit: int = 15000, since_days: int = 90) -> List[dict]:
    """Consulta PostgreSQL y arma pares usuario/asistente listos para analizar."""
    since = datetime.utcnow() - timedelta(days=since_days)

    # Consulta mensajes recientes ordenados por conversacion y fecha.
    query = (
        "SELECT agent_chat_id, message, created_at "
        "FROM chat_messages "
        "WHERE created_at >= %s "
        "ORDER BY agent_chat_id, created_at "
        "LIMIT %s"
    )

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (since, limit))
            rows = cursor.fetchall()

    conversations = []
    messages_by_chat = defaultdict(list)

    # Agrupa los mensajes por conversacion para poder emparejarlos en orden.
    for row in rows:
        agent_chat_id = row[0]
        message_json = row[1]
        created_at = row[2]
        messages_by_chat[agent_chat_id].append(
            {
                "message": message_json,
                "created_at": created_at,
            }
        )

    # Recorre cada conversacion y guarda pares: ultimo usuario + respuesta del asistente.
    for conversation_id, events in messages_by_chat.items():
        last_user_text = ""
        for event in sorted(events, key=lambda x: x["created_at"]):
            payload = event["message"]
            role = payload.get("role") if isinstance(payload, dict) else None
            text = extract_text_from_message(payload)
            if not text:
                continue
            if role == "user":
                last_user_text = text
            elif role == "assistant" and last_user_text:
                conversations.append(
                    {
                        "conversation_id": str(conversation_id),
                        "user_text": last_user_text,
                        "assistant_text": text,
                        "created_at": event["created_at"].isoformat(),
                    }
                )
                last_user_text = ""

    return conversations


def ingest(limit: int = 15000, since_days: int = 90) -> IngestResponse:
    """Ejecuta la ingesta y guarda el resultado en data/conversations.jsonl."""
    records = fetch_conversation_records(limit=limit, since_days=since_days)
    save_json_lines(records, OUTPUT_PATH)
    return IngestResponse(imported_records=len(records), output_file=str(OUTPUT_PATH))


@app.get("/health")
def health() -> dict:
    """Endpoint simple para confirmar que el servicio esta activo."""
    return {"status": "ok", "service": "ingest"}


@app.post("/ingest", response_model=IngestResponse)
def run_ingest(request: IngestRequest) -> IngestResponse:
    """Endpoint principal: recibe parametros y dispara la ingesta."""
    return ingest(limit=request.limit, since_days=request.since_days)


if __name__ == "__main__":
    import uvicorn

    # Levanta el servicio localmente en el puerto 8001.
    uvicorn.run("ingest_service:app", host="127.0.0.1", port=8001, log_level="info")
