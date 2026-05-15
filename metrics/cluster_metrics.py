from datetime import datetime
from pathlib import Path
from typing import Optional

from faq_common import DATA_DIR, load_json, save_json
from faq_models import SuggestionSummary

METRICS_DIR = DATA_DIR / "metrics"
METRICS_DIR.mkdir(exist_ok=True)


def save_run_metrics(summary: SuggestionSummary) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = METRICS_DIR / f"run_{timestamp}.json"
    metrics = {
        "run_at": datetime.utcnow().isoformat(),
        "company_count": summary.company_count,
        "cluster_count": summary.cluster_count,
        "total_examples": summary.total_examples,
        "average_cluster_size": summary.average_cluster_size,
        "silhouette_score": summary.silhouette_score,
    }
    save_json(metrics, path)
    return path


def load_all_metrics() -> list:
    runs = []
    for path in sorted(METRICS_DIR.glob("run_*.json")):
        try:
            runs.append(load_json(path))
        except Exception:
            continue
    return runs