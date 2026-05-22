import re
from typing import Dict, List, Optional

from faq_common import normalize_text

_nlp = None

# Prefijos comunes
_LOCATION_PREFIXES = {"san", "santa", "santo", "el", "la", "los", "las", "del", "de"}

# Preposiciones que indican destino/lugar
_LOCATIVE_PREPS = {"a", "en", "desde", "hasta", "hacia"}


def _get_nlp():
    global _nlp
    if _nlp is None:
        for model in ("es_core_news_md", "es_core_news_sm"):
            try:
                import spacy
                _nlp = spacy.load(model)
                break
            except Exception:
                continue
        if _nlp is None:
            _nlp = False
    return None if _nlp is False else _nlp


def _is_location_entity(ent, doc) -> bool:
    first_word = ent.text.lower().split()[0]
    if first_word in _LOCATION_PREFIXES:
        return True
    if ent.start > 0 and doc[ent.start - 1].lower_ in _LOCATIVE_PREPS:
        return True
    return False


def redact_personal_data(text: str, protected_terms: Optional[List[str]] = None) -> str:
    text = normalize_text(text)
    if not text:
        return ""

    protected_values: Dict[str, str] = {}
    for index, term in enumerate(protected_terms or []):
        clean_term = normalize_text(term)
        if clean_term:
            token = f"marca{index}"
            protected_values[token] = clean_term
            text = text.replace(clean_term, token)

    # Email y teléfono
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[correo]", text)
    text = re.sub(r"\b(?:\+?\d[\s-]?){7,}\b", "[telefono]", text)

    text = re.sub(
        r"((?i:hola|buenos dias|buenos días|buenas tardes|buenas noches)),?\s+"
        r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,1}",
        lambda m: m.group(1),
        text,
    )
    text = re.sub(
        r"((?i:gracias por escribir(?:nos)?)),?\s+"
        r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,1}",
        r"\1",
        text,
    )

    # NER para nombres de persona
    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text)
        spans_to_redact = [
            (ent.start_char, ent.end_char)
            for ent in doc.ents
            if ent.label_ == "PER" and not _is_location_entity(ent, doc)
        ]
        for start, end in reversed(spans_to_redact):
            text = text[:start] + "[persona]" + text[end:]
    else:
        # Fallback regex (menos preciso — puede redactar topónimos)
        text = re.sub(
            r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+o\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})+\b",
            "[personas]",
            text,
        )
        text = re.sub(
            r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})+\b",
            "[persona]",
            text,
        )
        text = re.sub(
            r"\b(para|de|a|por|con)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b",
            r"\1 [persona]",
            text,
        )

    for token, value in protected_values.items():
        text = text.replace(token, value)

    return normalize_text(text)
