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
