from services.suggestion.filters import is_good_faq_candidate


def test_rejects_trivial():
    assert not is_good_faq_candidate("hola")
    assert not is_good_faq_candidate("gracias")
    assert not is_good_faq_candidate("ok")


def test_rejects_too_short():
    assert not is_good_faq_candidate("precio?")


def test_rejects_email_in_text():
    assert not is_good_faq_candidate("cuál es el precio? escríbeme a juan@gym.com")


def test_rejects_no_business_intent():
    assert not is_good_faq_candidate("cómo estás hoy?")


def test_accepts_valid_question():
    assert is_good_faq_candidate("cuáles son los horarios de las clases de crossfit?")
    assert is_good_faq_candidate("cuánto cuesta el plan mensual?")
    assert is_good_faq_candidate("cómo puedo reservar una clase?")


def test_rejects_bot_templates():
    assert not is_good_faq_candidate(
        "Gracias por comunicarte con MOENA. En este momento no estamos disponibles, "
        "déjanos tu mensaje y te damos respuesta lo más pronto posible"
    )
    assert not is_good_faq_candidate(
        "Hola (Nombre Cliente) ¿Cómo has estado? lo cambias tu para cada mensaje"
    )


def test_rejects_away_message():
    assert not is_good_faq_candidate(
        "En este momento no estamos disponibles, deja tu mensaje"
    )