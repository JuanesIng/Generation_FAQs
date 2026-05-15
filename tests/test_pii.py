from services.suggestion.pii import redact_personal_data


def test_redacts_email():
    result = redact_personal_data("escríbeme a juan@empresa.com para más info")
    assert "juan@empresa.com" not in result
    assert "[correo]" in result


def test_redacts_phone():
    result = redact_personal_data("llámanos al 3001234567")
    assert "3001234567" not in result
    assert "[telefono]" in result


def test_keeps_protected_terms():
    result = redact_personal_data("hola CrossFit Norte", protected_terms=["CrossFit Norte"])
    assert "CrossFit Norte" in result


def test_empty_input():
    assert redact_personal_data("") == ""


def test_redacts_greeting_name():
    result = redact_personal_data("Hola María, cómo te podemos ayudar?")
    assert "María" not in result