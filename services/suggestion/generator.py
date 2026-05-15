import os
from typing import Any, List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from faq_common import normalize_text
from services.suggestion.pii import redact_personal_data

FAQ_LLM_MODEL = os.getenv("FAQ_LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
FAQ_LLM_ENABLED = os.getenv("FAQ_LLM_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


class AnswerGenerator:
    def __init__(self) -> None:
        self._embedding_model: Optional[SentenceTransformer] = None
        self._pipeline: Optional[Any] = None
        self._ready = False

    def load(self) -> None:
        if self._ready:
            return

        self._embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

        if FAQ_LLM_ENABLED:
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
                tokenizer = AutoTokenizer.from_pretrained(FAQ_LLM_MODEL)
                model = AutoModelForCausalLM.from_pretrained(FAQ_LLM_MODEL)
                self._pipeline = pipeline("text-generation", model=model, tokenizer=tokenizer)
            except Exception as exc:
                print(f"No se pudo cargar {FAQ_LLM_MODEL}. Se usará respuesta histórica. Error: {exc}")
                self._pipeline = None

        self._ready = True

    def encode(self, texts: List[str]) -> np.ndarray:
        return self._embedding_model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def most_common_answer(self, answers: List[str], protected_terms: Optional[List[str]] = None) -> str:
        clean_answers = [
            redact_personal_data(a, protected_terms=protected_terms)
            for a in answers
            if redact_personal_data(a, protected_terms=protected_terms)
        ]
        if not clean_answers:
            return "Respuesta sugerida basada en el contexto de la conversación."
        return max(set(clean_answers), key=clean_answers.count)

    def generate(
        self,
        question: str,
        examples: List[str],
        historical_answers: List[str],
        company_name: Optional[str],
    ) -> str:
        protected_terms = [company_name] if company_name else []
        fallback = self.most_common_answer(historical_answers, protected_terms=protected_terms)

        if not self._pipeline:
            return fallback

        clean_answers = [
            redact_personal_data(a, protected_terms=protected_terms)
            for a in historical_answers
            if redact_personal_data(a, protected_terms=protected_terms)
        ]
        clean_examples = [redact_personal_data(e) for e in examples if redact_personal_data(e)]
        answer_context = "\n".join(f"- {a}" for a in clean_answers[:4])
        example_context = "\n".join(f"- {e}" for e in clean_examples[:5])
        company_context = company_name or "esta empresa"

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un asistente que redacta respuestas de FAQ en español. "
                    "Usa solo la evidencia entregada, no mezcles empresas ni inventes datos. "
                    "No incluyas nombres, teléfonos, correos ni datos personales de clientes. "
                    "Si falta información, responde de forma prudente indicando que se debe confirmar con el equipo."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Empresa: {company_context}\n"
                    f"Pregunta FAQ propuesta: {question}\n\n"
                    f"Preguntas reales similares:\n{example_context}\n\n"
                    f"Respuestas históricas del asistente:\n{answer_context}\n\n"
                    "Redacta una respuesta final corta, clara y útil para una FAQ. "
                    "No menciones que analizaste conversaciones."
                ),
            },
        ]

        tokenizer = self._pipeline.tokenizer
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        generated = self._pipeline(
            prompt,
            max_new_tokens=180,
            do_sample=False,
            return_full_text=False,
            pad_token_id=tokenizer.eos_token_id,
        )
        answer = redact_personal_data(generated[0].get("generated_text", ""), protected_terms=protected_terms)
        return answer or fallback

    @property
    def embedding_model_name(self) -> str:
        return EMBEDDING_MODEL_NAME

    @property
    def llm_model_name(self) -> str:
        return FAQ_LLM_MODEL if self._pipeline else "historical_fallback"