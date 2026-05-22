import re
from typing import List

from faq_common import normalize_text


def is_good_faq_candidate(text: str) -> bool:
    text = normalize_text(text)
    lowered = text.lower().strip(" ¿?¡!.,;:")
    word_count = len(text.split())

    if len(text) < 10 or word_count < 2:
        return False
    if len(text) > 400:
        return False
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        return False
    if re.search(r"\b\d(?:[\s-]?\d){6,}\b", text):
        return False

    trivial_messages = {
        "hola", "buenas", "buenos dias", "buenos días",
        "buenas tardes", "buenas noches", "si", "sí",
        "no", "ok", "dale", "gracias", "listo", "claro",
        "perfecto", "entendido", "de acuerdo",
    }
    if lowered in trivial_messages:
        return False

    non_faq_fragments = (
        "quien soy", "quién soy", "que hora", "qué hora",
        "hora es actualmente", "este es el mensaje",
    )
    if any(fragment in lowered for fragment in non_faq_fragments):
        return False

    
    declarative_starters = (
        "esta es", "este es", "estas son", "estos son",
        "aqui esta", "aquí está", "aquí esta",
        "aca esta", "acá está", "acá esta",
        "ya envie", "ya envié", "ya realize",
        "ya realicé", "ya pague", "ya pagué",
    )
    if any(lowered.startswith(p) for p in declarative_starters) and "?" not in text:
        return False

    if "gracias" in lowered and word_count <= 5 and "?" not in text:
        return False

    bot_template_fragments = (
        "gracias por comunicarte con",
        "en este momento no estamos disponibles",
        "déjanos tu mensaje",
        "deja tu mensaje",
        "nombre cliente",
        "lo cambias tu para",
        "lo cambias tú para",
    )
    if any(frag in lowered for frag in bot_template_fragments):
        return False

    has_question_signal = "?" in text or any(
        lowered.startswith(prefix)
        for prefix in (
            "como ", "cómo ", "cuanto ", "cuánto ", "donde ", "dónde ",
            "cuando ", "cuándo ", "puedo ", "quiero ", "quisiera ",
            "necesito ", "tienen ", "me ayudas ", "me puedes ", "me puede ",
            "me gustaria ", "me gustaría ", "seria posible ", "sería posible ",
            "puedes ", "pueden ", "se puede ", "es posible ",
        )
    )

    intent_keywords = (

        "precio", "precios", "plan", "planes", "mensualidad",
        "horario", "horarios", "ubicacion", "ubicación",
        "direccion", "dirección", "reservar", "reserva",
        "agendar", "clase", "clases", "pagar", "pago",
        "qr", "crossfit", "informacion", "información",
        "cortesia", "cortesía", "membresía", "membresia",
        # Plataforma / funcionalidades
        "mensaje", "mensajes", "cliente", "clientes",
        "inactivo", "inactivos", "activo", "activos",
        "plataforma", "usuario", "usuarios", "contacto",
        "enviar", "mandar", "notificacion", "notificación",
        "reporte", "reportes", "acceso", "configurar",
        "integrar", "integracion", "integración", "bot",
        "automatico", "automático", "recordatorio", "cobro",
        "factura", "asistencia", "registro",
    )
    has_business_intent = any(keyword in lowered for keyword in intent_keywords)

    return has_business_intent or (has_question_signal and word_count >= 5)

def is_existing_faq(question: str, existing_questions: List[str], encode_fn, threshold: float = 0.78) -> bool:
    if not existing_questions:
        return False

    import numpy as np
    texts = [question, *existing_questions]
    embeddings = encode_fn(texts)
    similarities = embeddings[1:] @ embeddings[0]
    return bool(np.max(similarities) >= threshold)