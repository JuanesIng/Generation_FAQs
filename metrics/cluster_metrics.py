from datetime import datetime
from pathlib import Path
from typing import Optional

from faq_common import DATA_DIR, company_data_dir, load_json, save_json
from faq_models import SuggestionSummary

METRICS_DIR = DATA_DIR / "metrics"
METRICS_DIR.mkdir(exist_ok=True)


def _metrics_dir(company_id: Optional[str]) -> Path:
    if company_id:
        path = company_data_dir(company_id) / "metrics"
        path.mkdir(exist_ok=True)
        return path
    return METRICS_DIR


def save_run_metrics(summary: SuggestionSummary, company_id: Optional[str] = None) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = _metrics_dir(company_id) / f"run_{timestamp}.json"
    metrics = {
        "run_at": datetime.utcnow().isoformat(),
        "company_id": company_id,
        "company_count": summary.company_count,
        "cluster_count": summary.cluster_count,
        "total_examples": summary.total_examples,
        "average_cluster_size": summary.average_cluster_size,
        "avg_coherence_score": summary.avg_coherence_score,
        "avg_answer_relevance": summary.avg_answer_relevance,
    }
    save_json(metrics, path)
    return path


def load_all_metrics(company_id: Optional[str] = None) -> list:
    runs = []
    for path in sorted(_metrics_dir(company_id).glob("run_*.json")):
        try:
            runs.append(load_json(path))
        except Exception:
            continue
    return runs
