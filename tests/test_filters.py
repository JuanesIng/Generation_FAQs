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