from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from services.ingest_service import ingest
from services.suggestion.pipeline import build_suggestions, load_conversation_pairs
from services.suggestion.generator import AnswerGenerator

generator = AnswerGenerator()


def scheduled_pipeline() -> None:
    start = datetime.utcnow()
    print(f"[{start.isoformat()}] Iniciando pipeline de FAQ automática...")
    try:
        generator.load()

        ingest_response = ingest(limit=15000, since_days=180)
        print(f"  - Ingestados {ingest_response.imported_records} pares en conversations.jsonl")

        conversations = load_conversation_pairs()
        if not conversations:
            print("  - Sin conversaciones procesadas, saliendo.")
            return

        summary = build_suggestions(conversations, generator)
        print(f"  - Sugerencias generadas: {len(summary.suggestions)}")
        print(f"  - Silhouette: {summary.silhouette_score}")
        print(f"  - Clusters: {summary.cluster_count}")

    except Exception as exc:
        print(f"  - Pipeline falló: {exc}")

    print(f"[{datetime.utcnow().isoformat()}] Pipeline completada.")


if __name__ == "__main__":
    scheduler = BlockingScheduler()
    scheduler.add_job(scheduled_pipeline, "interval", hours=24, next_run_time=datetime.now())
    print("Scheduler iniciado: el job se ejecutará cada 24 horas.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler detenido manualmente.")