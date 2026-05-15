import re
from typing import Dict, List, Optional

from faq_common import normalize_text


def redact_personal_data(text: str, protected_terms: Optional[List[str]] = None) -> str:
    text = normalize_text(text)
    if not text:
        return ""

    protected_values: Dict[str, str] = {}
    for index, term in enumerate(protected_terms or []):
        clean_term = normalize_text(term)
        if clean_term:
            token = f"__PROTECTED_{index}__"
            protected_values[token] = clean_term
            text = text.replace(clean_term, token)

    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[correo]", text)
    text = re.sub(r"\b(?:\+?\d[\s-]?){7,}\b", "[telefono]", text)
    text = re.sub(
        r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+o\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})+\b",
        "[personas]",
        text,
    )
    text = re.sub(
        r"(?i)(hola|buenos dias|buenos días|buenas tardes|buenas noches),?\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3}",
        lambda match: match.group(1),
        text,
    )
    text = re.sub(
        r"(?i)(gracias por escribir(?:nos)?),?\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3}",
        r"\1",
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