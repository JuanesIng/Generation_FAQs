from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any, List

from fastapi import FastAPI

from faq_common import DATA_DIR, get_db_connection, json_text, normalize_text, save_json_lines
from faq_models import IngestRequest, IngestResponse

app = FastAPI(title="Everwod FAQ Ingestion Service")

OUTPUT_PATH = DATA_DIR / "conversations.jsonl"


def extract_text_from_message(payload: Any) -> str:
    if not payload:
        return ""
    return normalize_text(json_text(payload.get("content") if isinstance(payload, dict) else payload))


# def fetch_conversation_records(limit: int = 15000, since_days: int = 90) -> List[dict]:
#     since = datetime.utcnow() - timedelta(days=since_days)

#     query = (
#         "SELECT cm.agent_chat_id, cm.message, cm.created_at, ac.workspace_id, w.name "
#         "FROM chat_messages cm "
#         "JOIN agent_chats ac ON ac.id = cm.agent_chat_id "
#         "LEFT JOIN workspaces w ON w.id = ac.workspace_id "
#         "WHERE cm.created_at >= %s "
#         "ORDER BY ac.workspace_id, cm.agent_chat_id, cm.created_at "
#         "LIMIT %s"
#     )

#     with get_db_connection() as conn:
#         with conn.cursor() as cursor:
#             cursor.execute(query, (since, limit))
#             rows = cursor.fetchall()

#     conversations = []
#     messages_by_chat = defaultdict(list)

#     for row in rows:
#         agent_chat_id, message_json, created_at, workspace_id, workspace_name = row
#         messages_by_chat[agent_chat_id].append({
#             "message": message_json,
#             "created_at": created_at,
#             "company_id": str(workspace_id) if workspace_id is not None else "unknown",
#             "company_name": workspace_name,
#         })

#     for conversation_id, events in messages_by_chat.items():
#         last_user_text = ""
#         for event in sorted(events, key=lambda x: x["created_at"]):
#             payload = event["message"]
#             role = payload.get("role") if isinstance(payload, dict) else None
#             text = extract_text_from_message(payload)
#             if not text:
#                 continue
#             if role == "user":
#                 last_user_text = text
#             elif role == "assistant" and last_user_text:
#                 conversations.append({
#                     "company_id": event["company_id"],
#                     "company_name": event["company_name"],
#                     "conversation_id": str(conversation_id),
#                     "user_text": last_user_text,
#                     "assistant_text": text,
#                     "created_at": event["created_at"].isoformat(),
#                 })
#                 last_user_text = ""

#     return conversations

def fetch_conversation_records(limit: int = 15000, since_days: int = 180) -> List[dict]:
    since = datetime.utcnow() - timedelta(days=since_days)

    # FIX 1: El LIMIT ahora aplica sobre conversaciones distintas, no mensajes.
    # Primero obtenemos los IDs de conversaciones elegibles...
    id_query = (
        "SELECT DISTINCT cm.agent_chat_id "
        "FROM chat_messages cm "
        "JOIN agent_chats ac ON ac.id = cm.agent_chat_id "
        "WHERE cm.created_at >= %s "
        "LIMIT %s"
    )

    # ...luego traemos TODOS sus mensajes sin límite artificial.
    msg_query = (
        "SELECT cm.agent_chat_id, cm.message, cm.created_at, ac.workspace_id, w.name "
        "FROM chat_messages cm "
        "JOIN agent_chats ac ON ac.id = cm.agent_chat_id "
        "LEFT JOIN workspaces w ON w.id = ac.workspace_id "
        "WHERE cm.agent_chat_id = ANY(%s) "
        "ORDER BY ac.workspace_id, cm.agent_chat_id, cm.created_at"
    )

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(id_query, (since, limit))
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
        
        # FIX 2: Acumulamos todos los turnos de usuario consecutivos antes
        # de un assistant, en lugar de solo el último.
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

def ingest(limit: int = 15000, since_days: int = 90) -> IngestResponse:
    records = fetch_conversation_records(limit=limit, since_days=since_days)
    save_json_lines(records, OUTPUT_PATH)
    return IngestResponse(imported_records=len(records), output_file=str(OUTPUT_PATH))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ingest"}


@app.post("/ingest", response_model=IngestResponse)
def run_ingest(request: IngestRequest) -> IngestResponse:
    return ingest(limit=request.limit, since_days=request.since_days)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.ingest_service:app", host="127.0.0.1", port=8001, log_level="info")