import numpy as np
from unittest.mock import MagicMock

from services.suggestion.filters import is_existing_faq


def make_encode_fn(vectors):
    def encode(texts):
        return np.array([vectors[i % len(vectors)] for i in range(len(texts))], dtype=float)
    return encode


def test_returns_false_when_no_existing():
    encode_fn = MagicMock(return_value=np.array([[1.0, 0.0]]))
    assert not is_existing_faq("cualquier pregunta", [], encode_fn)


def test_detects_duplicate():
    vec = np.array([1.0, 0.0])
    encode_fn = lambda texts: np.array([vec for _ in texts])
    assert is_existing_faq("pregunta", ["pregunta similar"], encode_fn, threshold=0.78)


def test_no_duplicate_when_different():
    def encode_fn(texts):
        vectors = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
        return np.array([vectors[i % 2] for i in range(len(texts))])
    assert not is_existing_faq("pregunta A", ["pregunta B"], encode_fn, threshold=0.78)