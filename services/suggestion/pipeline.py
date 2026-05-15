import os
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

from faq_common import DATA_DIR, get_db_connection, load_json_lines, normalize_text, save_json
from faq_models import SuggestionResponse, SuggestionSummary
from services.suggestion.filters import is_existing_faq, is_good_faq_candidate
from services.suggestion.clustering import (
    build_clusters,
    compute_silhouette,
    compute_support,
    get_centroid_index,
    get_cluster_groups,
)
from services.suggestion.generator import AnswerGenerator
from services.suggestion.pii import redact_personal_data

FAQ_CLUSTER_EPS = float(os.getenv("FAQ_CLUSTER_EPS", "0.34"))
FAQ_MIN_CLUSTER_SIZE = int(os.getenv("FAQ_MIN_CLUSTER_SIZE", "3"))
FAQ_SKIP_EXISTING = os.getenv("FAQ_SKIP_EXISTING", "true").lower() in {"1", "true", "yes", "on"}
FAQ_DUPLICATE_THRESHOLD = float(os.getenv("FAQ_DUPLICATE_THRESHOLD", "0.78"))
FAQ_MIN_SUPPORT = float(os.getenv("FAQ_MIN_SUPPORT", "0.68"))

SUGGESTIONS_PATH = DATA_DIR / "faq_suggestions.json"
CONVERSATIONS_PATH = DATA_DIR / "conversations.jsonl"


def company_key(item: Dict[str, str]) -> str:
    return normalize_text(str(item.get("company_id") or item.get("workspace_id") or "unknown"))


def load_conversation_pairs() -> List[Dict[str, str]]:
    if not CONVERSATIONS_PATH.exists():
        raise FileNotFoundError(f"Conversation file not found: {CONVERSATIONS_PATH}")
    return load_json_lines(CONVERSATIONS_PATH)


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
) -> Tuple[List[SuggestionResponse], Optional[float]]:
    existing_questions = existing_questions or []

    valid_items = [
        {**item, "user_text": normalize_text(item.get("user_text", ""))}
        for item in conversations
        if is_good_faq_candidate(normalize_text(item.get("user_text", "")))
    ]

    if len(valid_items) < FAQ_MIN_CLUSTER_SIZE:
        return [], None

    user_texts = [item["user_text"] for item in valid_items]
    embeddings = generator.encode(user_texts)
    labels = build_clusters(embeddings, eps=FAQ_CLUSTER_EPS, min_samples=FAQ_MIN_CLUSTER_SIZE)
    cluster_groups = get_cluster_groups(labels)

    suggestions: List[SuggestionResponse] = []

    for indices in cluster_groups.values():
        best_index = get_centroid_index(indices, embeddings)
        question_text = user_texts[best_index]
        representative = valid_items[best_index]

        if is_existing_faq(question_text, existing_questions, generator.encode, FAQ_DUPLICATE_THRESHOLD):
            continue

        support = compute_support(indices, embeddings)
        if support < FAQ_MIN_SUPPORT:
            continue

        examples = []
        for idx in indices[:5]:
            candidate = redact_personal_data(user_texts[idx])
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
            company_name=representative.get("company_name"),
        )

        cluster_score = round(min(100.0, 100.0 * len(indices) / len(valid_items)), 2)

        suggestions.append(SuggestionResponse(
            id=str(uuid.uuid4()),
            company_id=company_key(representative),
            company_name=representative.get("company_name"),
            question=question_text,
            answer=answer_text,
            cluster_size=len(indices),
            support_examples=examples[:3],
            cluster_score=cluster_score,
        ))

    return suggestions, compute_silhouette(embeddings, labels)


def build_suggestions(conversations: List[Dict[str, str]], generator: AnswerGenerator) -> SuggestionSummary:
    if not conversations:
        raise ValueError("No conversation pairs available.")

    conversations_by_company: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for item in conversations:
        conversations_by_company[company_key(item)].append(item)

    suggestions: List[SuggestionResponse] = []
    silhouettes = []
    total_examples = 0
    existing_faqs = load_existing_faqs_by_company()

    for company_id, items in conversations_by_company.items():
        total_examples += sum(1 for item in items if is_good_faq_candidate(item.get("user_text", "")))
        company_suggestions, silhouette = build_company_suggestions(
            items,
            generator=generator,
            existing_questions=existing_faqs.get(company_id, []),
        )
        suggestions.extend(company_suggestions)
        if silhouette is not None:
            silhouettes.append(silhouette)

    if not suggestions:
        raise ValueError("Insufficient data to generate FAQ suggestions.")

    summary = SuggestionSummary(
        company_count=len(conversations_by_company),
        cluster_count=len(suggestions),
        total_examples=total_examples,
        average_cluster_size=round(total_examples / len(suggestions), 2),
        silhouette_score=round(sum(silhouettes) / len(silhouettes), 4) if silhouettes else None,
        suggestions=suggestions,
    )
    save_json(summary.dict(), SUGGESTIONS_PATH)
    return summary