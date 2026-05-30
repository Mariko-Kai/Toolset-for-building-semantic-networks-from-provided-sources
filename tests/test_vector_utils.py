"""Тесты pipeline.vector_utils (ТЗ Этап 3.1)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from pipeline.vector_utils import (
    cosine_similarity_matrix,
    find_similar_pairs,
    normalize_rows,
    rank_by_query,
)


def test_cosine_matrix_matches_manual():
    embs = [[1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    S = cosine_similarity_matrix(embs)
    assert S.shape == (3, 3)
    # диагональ = 1 (с точностью до плавающей точки)
    assert np.allclose(np.diag(S), 1.0)
    # cos между [1,0] и [1,1] = 1/sqrt(2)
    assert math.isclose(S[0, 1], 1 / math.sqrt(2), rel_tol=1e-9)
    # cos между [1,0] и [0,1] = 0
    assert math.isclose(S[0, 2], 0.0, abs_tol=1e-12)


def test_zero_vector_safe():
    S = cosine_similarity_matrix([[0.0, 0.0], [1.0, 1.0]])
    assert math.isclose(S[0, 1], 0.0, abs_tol=1e-12)  # нулевой вектор -> сходство 0


def test_find_similar_pairs_threshold():
    embs = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]
    pairs = find_similar_pairs(embs, threshold=0.9)
    assert [(i, j) for i, j, _ in pairs] == [(0, 1)]
    assert pairs[0][2] > 0.9


def test_find_similar_pairs_respects_roles():
    embs = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]  # все идентичны
    roles = ["def", "prop", "def"]
    pairs = find_similar_pairs(embs, threshold=0.5, roles=roles)
    # из трёх идентичных только пара одинаковой роли (0,2) проходит
    assert [(i, j) for i, j, _ in pairs] == [(0, 2)]


def test_find_similar_pairs_matches_naive():
    rng = np.random.default_rng(0)
    embs = rng.normal(size=(20, 8)).tolist()
    th = 0.5
    fast = {(i, j) for i, j, _ in find_similar_pairs(embs, th)}

    def naive_cos(a, b):
        a, b = np.array(a), np.array(b)
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    naive = {(i, j) for i in range(20) for j in range(i + 1, 20) if naive_cos(embs[i], embs[j]) > th}
    assert fast == naive


def test_ragged_raises():
    with pytest.raises(ValueError):
        cosine_similarity_matrix([[1.0, 0.0], [1.0]])


def test_rank_by_query_orders_and_filters():
    embs = [[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]]
    ranked = rank_by_query([1.0, 0.0], embs, min_sim=0.5)
    # ближе всего idx 0, затем idx 2; idx 1 (ортогональный) отфильтрован
    assert [i for i, _ in ranked] == [0, 2]
    assert ranked[0][1] >= ranked[1][1]


def test_rank_by_query_top_k():
    embs = [[1.0, 0.0]] * 10
    ranked = rank_by_query([1.0, 0.0], embs, min_sim=0.0, top_k=3)
    assert len(ranked) == 3


def test_rank_by_query_dim_mismatch_returns_empty():
    assert rank_by_query([1.0, 0.0, 0.0], [[1.0, 0.0]], min_sim=0.0) == []
    assert rank_by_query([1.0, 0.0], [], min_sim=0.0) == []


def test_normalize_rows():
    out = normalize_rows(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert np.allclose(out[0], [0.6, 0.8])
    assert np.allclose(out[1], [0.0, 0.0])
