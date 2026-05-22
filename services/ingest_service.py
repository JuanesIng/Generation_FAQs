import asyncio
import json
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from faq_common import DATA_DIR, company_data_dir, get_db_connection, json_text, normalize_text, save_json_lines
from faq_models import CompanyInfo, IngestRequest, IngestResponse

app = FastAPI(title="Everwod FAQ Ingestion Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_PATH = DATA_DIR / "conversations.jsonl"


def extract_text_from_message(payload: Any) -> str:
    if not payload:
        return ""
    return normalize_text(json_text(payload.get("content") if isinstance(payload, dict) else payload))

def fetch_conversation_records(
    limit: int = 15000,
    since_days: int = 180,
    company_id: Optional[str] = None,
) -> List[dict]:
    since = datetime.utcnow() - timedelta(days=since_days)

    company_clause = "AND ac.workspace_id::text = %s " if company_id else ""
    id_query = (
        "SELECT DISTINCT cm.agent_chat_id "
        "FROM chat_messages cm "
        "JOIN agent_chats ac ON ac.id = cm.agent_chat_id "
        f"WHERE cm.created_at >= %s {company_clause}"
        "LIMIT %s"
    )

    msg_query = (
        "SELECT cm.agent_chat_id, cm.message, cm.created_at, ac.workspace_id, w.name "
        "FROM chat_messages cm "
        "JOIN agent_chats ac ON ac.id = cm.agent_chat_id "
        "LEFT JOIN workspaces w ON w.id = ac.workspace_id "
        "WHERE cm.agent_chat_id = ANY(%s::uuid[]) "
        "ORDER BY ac.workspace_id, cm.agent_chat_id, cm.created_at"
    )

    id_params: List[Any] = [since]
    if company_id:
        id_params.append(company_id)
    id_params.append(limit)

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(id_query, id_params)
            chat_ids = [row[0] for row in cursor.fetchall()]

            if not chat_ids:
                return []

            cursor.execute(msg_query, (chat_ids,))
            rows = cursor.fetchall()

    messages_by_chat = defaultdict(list)
    for row in rows:
        agent_chat_id, message_json, created_at, workspace_id, workspace_name = row
        messages_by_chat[agent_chat_id].append({
            "message": message_json,
            "created_at": created_at,
            "company_id": str(workspace_id) if workspace_id is not None else "unknown",
            "company_name": workspace_name,
        })

    conversations = []
    for conversation_id, events in messages_by_chat.items():
        sorted_events = sorted(events, key=lambda x: x["created_at"])
        
        pending_user_texts = []

        for event in sorted_events:
            payload = event["message"]
            role = payload.get("role") if isinstance(payload, dict) else None
            text = extract_text_from_message(payload)

            if not text:
                continue

            if role == "user":
                pending_user_texts.append(text)

            elif role == "assistant" and pending_user_texts:
                # Unimos turnos de usuario consecutivos si los hay
                combined_user_text = " ".join(pending_user_texts)
                conversations.append({
                    "company_id": event["company_id"],
                    "company_name": event["company_name"],
                    "conversation_id": str(conversation_id),
                    "user_text": combined_user_text,
                    "assistant_text": text,
                    "created_at": event["created_at"].isoformat(),
                })
                pending_user_texts = []  # reset solo tras emparejar

    return conversations

def ingest(
    limit: int = 15000,
    since_days: int = 180,
    company_id: Optional[str] = None,
) -> IngestResponse:
    records = fetch_conversation_records(limit=limit, since_days=since_days, company_id=company_id)
    output_path = (company_data_dir(company_id) / "conversations.jsonl") if company_id else OUTPUT_PATH
    save_json_lines(records, output_path)
    return IngestResponse(imported_records=len(records), output_file=str(output_path))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ingest"}


@app.get("/companies")
def list_companies(since_days: int = 180) -> List[CompanyInfo]:
    since = datetime.utcnow() - timedelta(days=since_days)
    query = (
        "SELECT DISTINCT w.id::text, w.name "
        "FROM workspaces w "
        "JOIN agent_chats ac ON ac.workspace_id = w.id "
        "JOIN chat_messages cm ON cm.agent_chat_id = ac.id "
        "WHERE cm.created_at >= %s "
        "ORDER BY w.name"
    )
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (since,))
            rows = cursor.fetchall()
    return [CompanyInfo(id=str(row[0]), name=row[1]) for row in rows]


@app.post("/ingest", response_model=IngestResponse)
def run_ingest(request: IngestRequest) -> IngestResponse:
    return ingest(limit=request.limit, since_days=request.since_days, company_id=request.company_id)


@app.get("/ingest/stream")
async def ingest_stream(limit: int = 15000, since_days: int = 180, company_id: Optional[str] = None):
    
    _steps = [
        "Conectando a la base de datos",
        "Consultando conversaciones",
        "Procesando mensajes",
    ]

    async def event_stream():
        step_i = 0
        yield f"data: {json.dumps({'step': 'Iniciando ingesta...'})}\n\n"
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            None, lambda: ingest(limit=limit, since_days=since_days, company_id=company_id)
        )
        while not future.done():
            yield f"data: {json.dumps({'step': _steps[step_i % len(_steps)] + '...'})}\n\n"
            step_i += 1
            await asyncio.sleep(3)
        try:
            result = future.result()
            yield f"data: {json.dumps({'step': f'{result.imported_records} pares importados correctamente.', 'records': result.imported_records, 'done': True})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.ingest_service:app", host="127.0.0.1", port=8001, log_level="info")