import os
import re
import uuid
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

from faq_common import DATA_DIR, company_data_dir, get_db_connection, load_json_lines, normalize_text, save_json
from faq_models import SuggestionResponse, SuggestionSummary
from metrics.cluster_metrics import save_run_metrics
from services.suggestion.filters import is_existing_faq, is_good_faq_candidate
from services.suggestion.clustering import (
    build_clusters,
    compute_support,
    get_centroid_index,
    get_cluster_groups,
)
from services.suggestion.generator import AnswerGenerator
from services.suggestion.pii import redact_personal_data

FAQ_CLUSTER_ALGO = os.getenv("FAQ_CLUSTER_ALGO", "hdbscan")
FAQ_CLUSTER_EPS = float(os.getenv("FAQ_CLUSTER_EPS", "0.34"))
FAQ_MIN_CLUSTER_SIZE = int(os.getenv("FAQ_MIN_CLUSTER_SIZE", "3"))
FAQ_MAX_CLUSTER_SIZE = int(os.getenv("FAQ_MAX_CLUSTER_SIZE", "50"))
FAQ_SKIP_EXISTING = os.getenv("FAQ_SKIP_EXISTING", "true").lower() in {"1", "true", "yes", "on"}
FAQ_DUPLICATE_THRESHOLD = float(os.getenv("FAQ_DUPLICATE_THRESHOLD", "0.78"))
FAQ_MIN_SUPPORT = float(os.getenv("FAQ_MIN_SUPPORT", "0.68"))

_GLOBAL_SUGGESTIONS_PATH = DATA_DIR / "faq_suggestions.json"
_GLOBAL_CONVERSATIONS_PATH = DATA_DIR / "conversations.jsonl"


def _suggestions_path(company_id: Optional[str]):
    return (company_data_dir(company_id) / "suggestions.json") if company_id else _GLOBAL_SUGGESTIONS_PATH


def _conversations_path(company_id: Optional[str]):
    return (company_data_dir(company_id) / "conversations.jsonl") if company_id else _GLOBAL_CONVERSATIONS_PATH


def company_key(item: Dict[str, str]) -> str:
    return normalize_text(str(item.get("company_id") or item.get("workspace_id") or "unknown"))


def load_conversation_pairs(company_id: Optional[str] = None) -> List[Dict[str, str]]:
    path = _conversations_path(company_id)
    if not path.exists():
        raise FileNotFoundError(f"Conversation file not found: {path}")
    return load_json_lines(path)


def load_existing_faqs_by_company() -> Dict[str, List[str]]:
    if not FAQ_SKIP_EXISTING:
        return {}

    query = (
        "SELECT a.workspace_id, af.question "
        "FROM agent_faqs af "
        "JOIN agents a ON a.id = af.agent_id "
        "WHERE af.deleted_at IS NULL AND af.question IS NOT NULL"
    )

    faqs_by_company: Dict[str, List[str]] = defaultdict(list)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                for workspace_id, question in cursor.fetchall():
                    clean = normalize_text(question)
                    if clean:
                        faqs_by_company[str(workspace_id)].append(clean)
    except Exception as exc:
        print(f"No se pudieron cargar FAQs existentes. Error: {exc}")

    return faqs_by_company


def build_company_suggestions(
    conversations: List[Dict[str, str]],
    generator: AnswerGenerator,
    existing_questions: Optional[List[str]] = None,
) -> List[SuggestionResponse]:
    existing_questions = existing_questions or []

    valid_items = [
        {**item, "user_text": normalize_text(item.get("user_text", ""))}
        for item in conversations
        if is_good_faq_candidate(normalize_text(item.get("user_text", "")))
    ]

    if len(valid_items) < FAQ_MIN_CLUSTER_SIZE:
        return []

    user_texts = [item["user_text"] for item in valid_items]
    embeddings = generator.encode(user_texts)
    labels = build_clusters(
        embeddings,
        algo=FAQ_CLUSTER_ALGO,
        min_cluster_size=FAQ_MIN_CLUSTER_SIZE,
        eps=FAQ_CLUSTER_EPS,
    )
    cluster_groups = get_cluster_groups(labels)

    suggestions: List[SuggestionResponse] = []

    for indices in cluster_groups.values():
        if len(indices) > FAQ_MAX_CLUSTER_SIZE:
            continue

        best_index = get_centroid_index(indices, embeddings, texts=user_texts)
        question_text = user_texts[best_index]
        representative = valid_items[best_index]
        company_name = representative.get("company_name")

        if re.search(r'\[.+?\]', question_text):
            continue

        if is_existing_faq(question_text, existing_questions, generator.encode, FAQ_DUPLICATE_THRESHOLD):
            continue

        coherence_score = compute_support(indices, embeddings)
        if coherence_score < FAQ_MIN_SUPPORT:
            continue

        examples = []
        for idx in indices[:5]:
            candidate = redact_personal_data(user_texts[idx], protected_terms=[company_name] if company_name else [])
            if candidate not in examples:
                examples.append(candidate)

        answers = [
            normalize_text(valid_items[i].get("assistant_text", ""))
            for i in indices
            if normalize_text(valid_items[i].get("assistant_text", ""))
        ]

        answer_text = generator.generate(
            question=question_text,
            examples=examples,
            historical_answers=answers,
            company_name=company_name,
        )

        if re.search(r'\[.+?\]', answer_text):
            continue

        answer_emb = generator.encode([answer_text])[0]
        answer_emb_norm = answer_emb / np.linalg.norm(answer_emb)
        answer_relevance = round(float(np.dot(embeddings[best_index], answer_emb_norm)), 4)

        cluster_score = round(min(100.0, 100.0 * len(indices) / len(valid_items)), 2)
        clean_question = redact_personal_data(question_text, protected_terms=[company_name] if company_name else [])

        suggestions.append(SuggestionResponse(
            id=str(uuid.uuid4()),
            company_id=company_key(representative),
            company_name=company_name,
            question=clean_question,
            answer=answer_text,
            cluster_size=len(indices),
            support_examples=examples[:3],
            cluster_score=cluster_score,
            coherence_score=coherence_score,
            answer_relevance=answer_relevance,
        ))

    return suggestions


def build_suggestions(
    conversations: List[Dict[str, str]],
    generator: AnswerGenerator,
    company_id: Optional[str] = None,
) -> SuggestionSummary:
    if not conversations:
        raise ValueError("No hay conversaciones disponibles.")

    conversations_by_company: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for item in conversations:
        conversations_by_company[company_key(item)].append(item)

    suggestions: List[SuggestionResponse] = []
    total_examples = 0
    existing_faqs = load_existing_faqs_by_company()

    for cid, items in conversations_by_company.items():
        total_examples += sum(1 for item in items if is_good_faq_candidate(item.get("user_text", "")))
        company_suggestions = build_company_suggestions(
            items,
            generator=generator,
            existing_questions=existing_faqs.get(cid, []),
        )
        suggestions.extend(company_suggestions)

    if not suggestions:
        raise ValueError("Información insuficiente para generar FAQs.")

    avg_cluster = round(sum(s.cluster_size for s in suggestions) / len(suggestions), 2)
    avg_coherence = round(sum(s.coherence_score for s in suggestions) / len(suggestions), 4)
    avg_relevance = round(sum(s.answer_relevance for s in suggestions) / len(suggestions), 4)

    summary = SuggestionSummary(
        company_count=len(conversations_by_company),
        cluster_count=len(suggestions),
        total_examples=total_examples,
        average_cluster_size=avg_cluster,
        avg_coherence_score=avg_coherence,
        avg_answer_relevance=avg_relevance,
        suggestions=suggestions,
    )
    save_json(summary.dict(), _suggestions_path(company_id))
    save_run_metrics(summary, company_id)
    return summary
