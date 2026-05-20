from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from services.ingest_service import ingest, list_companies
from services.suggestion.pipeline import build_suggestions, load_conversation_pairs
from services.suggestion.generator import AnswerGenerator

generator = AnswerGenerator()


def scheduled_pipeline() -> None:
    start = datetime.utcnow()
    print(f"[{start.isoformat()}] Iniciando pipeline de FAQ automática...")
    try:
        generator.load()

        companies = list_companies(since_days=180)
        if not companies:
            print("  - No se encontraron empresas con actividad reciente.")
            return

        print(f"  - {len(companies)} empresas encontradas.")

        for company in companies:
            label = f"{company.name or company.id}"
            print(f"\n  [{label}]")
            try:
                ingest_response = ingest(limit=15000, since_days=180, company_id=company.id)
                print(f"    - Ingestados {ingest_response.imported_records} pares")

                conversations = load_conversation_pairs(company.id)
                if not conversations:
                    print("    - Sin conversaciones, saltando.")
                    continue

                summary = build_suggestions(conversations, generator, company.id)
                print(f"    - Sugerencias generadas: {summary.cluster_count}")
                print(f"    - Silhouette: {summary.silhouette_score}")

            except Exception as exc:
                print(f"    - Falló para {label}: {exc}")

    except Exception as exc:
        print(f"  - Pipeline falló: {exc}")

    print(f"\n[{datetime.utcnow().isoformat()}] Pipeline completada.")


if __name__ == "__main__":
    scheduler = BlockingScheduler()
    scheduler.add_job(scheduled_pipeline, "interval", hours=24, next_run_time=datetime.now())
    print("Scheduler iniciado: el job se ejecutará cada 24 horas.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler detenido manualmente.")
