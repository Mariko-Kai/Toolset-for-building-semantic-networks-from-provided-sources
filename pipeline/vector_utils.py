"""Векторные утилиты (ТЗ Этап 3.1) — производительность вне ИИ.

Заменяют питоновский O(n²) попарный косинус на векторизованную матрицу сходства
(numpy). Чистые функции без сети/LLM — легко тестируются.
"""
from __future__ import annotations

import numpy as np


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    """Нормирует строки матрицы (L2). Нулевые строки остаются нулевыми."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def cosine_similarity_matrix(embeddings) -> np.ndarray:
    """Матрица попарных косинусных сходств S[i,j] для списка эмбеддингов.

    Эквивалентно нормированному X @ X.T. Векторизовано: один matmul вместо
    O(n²) питоновских вызовов с пересчётом норм.
    """
    x = np.asarray(embeddings, dtype=np.float64)
    if x.ndim != 2:
        raise ValueError("embeddings должны быть прямоугольной матрицей (n x d)")
    xn = normalize_rows(x)
    return xn @ xn.T


def rank_by_query(query_vec, embeddings, min_sim: float = 0.0, top_k=None) -> list[tuple[int, float]]:
    """Ранжирует эмбеддинги по косинусной близости к query_vec.

    Возвращает [(idx, sim), ...] по убыванию sim, оставляя только sim>min_sim.
    Векторизовано (один matmul). При top_k использует argpartition (частичная
    сортировка) — сублинейно относительно полной сортировки. Возвращает [] при
    несовпадении размерностей или пустом входе.
    """
    n = len(embeddings)
    if n == 0:
        return []
    x = np.asarray(embeddings, dtype=np.float64)
    q = np.asarray(query_vec, dtype=np.float64)
    if x.ndim != 2 or q.ndim != 1 or x.shape[1] != q.shape[0]:
        return []
    xn = normalize_rows(x)
    qn = q / (np.linalg.norm(q) or 1.0)
    sims = xn @ qn
    idx = np.where(sims > min_sim)[0]
    if idx.size == 0:
        return []
    if top_k is not None and idx.size > top_k:
        idx = idx[np.argpartition(-sims[idx], top_k)[:top_k]]
    order = idx[np.argsort(-sims[idx])]
    return [(int(i), float(sims[i])) for i in order]


def find_similar_pairs(embeddings, threshold: float, roles=None) -> list[tuple[int, int, float]]:
    """Возвращает пары (i, j, sim) с i<j и sim>threshold.

    Если задан `roles` (список той же длины), оставляет только пары одной роли.
    Поиск кандидатов — векторизованный (верхний треугольник матрицы сходства),
    без двойного питоновского цикла по всем парам.
    """
    n = len(embeddings)
    if n < 2:
        return []
    sim = cosine_similarity_matrix(embeddings)
    iu = np.triu_indices(n, k=1)
    sims = sim[iu]
    mask = sims > threshold
    rows = iu[0][mask]
    cols = iu[1][mask]
    vals = sims[mask]
    pairs: list[tuple[int, int, float]] = []
    for i, j, s in zip(rows.tolist(), cols.tolist(), vals.tolist()):
        if roles is not None and roles[i] != roles[j]:
            continue
        pairs.append((i, j, s))
    return pairs
