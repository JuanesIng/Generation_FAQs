import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List

from dotenv import load_dotenv
import psycopg2

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

ENV_PATH = ROOT_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)


def get_db_config() -> Dict[str, str]:
    return {
        "dbname": os.getenv("DB_NAME", "everwod_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }


@contextmanager
def get_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    conn = psycopg2.connect(**get_db_config())
    try:
        yield conn
    finally:
        conn.close()


def json_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        if "value" in payload:
            return json_text(payload["value"])
        if "text" in payload:
            return json_text(payload["text"])
        if "content" in payload:
            return json_text(payload["content"])
        parts = [json_text(value) for value in payload.values()]
        return " ".join(part for part in parts if part)
    if isinstance(payload, list):
        parts = [json_text(item) for item in payload]
        return " ".join(part for part in parts if part)
    return str(payload).strip()


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split()) if text else ""


def save_json(data: Any, path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def save_json_lines(records: List[Dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_lines(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if payload:
                records.append(json.loads(payload))
    return records


def company_data_dir(company_id: str) -> Path:
    """Devuelve (y crea si no existe) el directorio de datos de una empresa."""
    path = DATA_DIR / "companies" / company_id
    path.mkdir(parents=True, exist_ok=True)
    return path