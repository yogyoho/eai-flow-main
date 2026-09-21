"""DBSCAN clustering over vectorized goods samples (numpy-only, no scikit-learn).

Density-based clustering on cosine distance. DBSCAN is chosen because the number
of distinct products is unknown and it explicitly marks outliers as noise (-1),
which surfaces anomalous prices for review rather than forcing them into a cluster.

Pure numpy: pairwise cosine distance matrix + a textbook DBSCAN expansion.
"""

from dataclasses import dataclass

import numpy as np

from scripts.clustering.vectorizer import Vectorizer, spec_extract


@dataclass
class ClusterResult:
    labels: list[int]  # -1 == noise / outlier
    representatives: dict[int, str]  # cluster label -> a representative goods name


def _cosine_distance_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normalized = matrix / norms
    sim = normalized @ normalized.T
    return 1.0 - np.clip(sim, -1.0, 1.0)


def _spec_similarity(a: set[str], b: set[str]) -> float:
    """规格 token 集合 Jaccard;AND 门限的规格半边。

    双方无 token → 1.0(不设门槛,与 v1 纯名称行为一致);
    一方缺失   → 0.0(未知 ≠ 匹配:无规格的行不得混入有规格簇的统计)。
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _pairwise_distance(samples: list[tuple[str, dict]], vec: Vectorizer) -> np.ndarray:
    """"同一商品" = 名称相似 **且** 规格匹配 → d = max(名称余弦距离, 规格Jaccard距离)。

    名称相似度在剥掉规格 token 的纯名称上计算(规格有独立门限,不重复计分);
    剥完为空的名称回退原文。min(相似度) 的 AND 语义: 同名不同规格与不同名
    同规格都分不开,只有两者都达标才落进 eps。
    ponytail: O(n²) 纯 python Jaccard,504 行 <2s,真慢了再换稀疏矩阵。
    """
    n = len(samples)
    name_texts: list[str] = []
    tok_sets: list[set[str]] = []
    for (name, _), (toks, stripped) in zip(samples, [spec_extract(x[0]) for x in samples]):
        name_texts.append(stripped or name)  # 剥完为空(名称纯规格)回退原文
        tok_sets.append(set(toks))
    samples_text = [(name_texts[i], samples[i][1]) for i in range(n)]
    vec.fit(samples_text)
    text = np.array([vec.transform(name, params) for name, params in samples_text])
    text_d = _cosine_distance_matrix(text)
    dist = np.empty((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            if i == j:
                dist[i, j] = 0.0
                continue
            dist[i, j] = max(text_d[i, j], 1.0 - _spec_similarity(tok_sets[i], tok_sets[j]))
    return dist


def _dbscan(distance: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    n = distance.shape[0]
    labels = np.full(n, -2, dtype=int)  # -2 = unvisited
    cluster_id = -1  # noise label is -1; real clusters start at 0

    for start in range(n):
        if labels[start] != -2:
            continue
        neighbors = list(np.where(distance[start] <= eps)[0])
        if len(neighbors) < min_samples:
            labels[start] = -1  # noise (may be reclaimed later as a border point)
            continue
        cluster_id += 1
        labels[start] = cluster_id
        seeds = [p for p in neighbors if p != start]
        i = 0
        while i < len(seeds):
            p = seeds[i]
            i += 1
            if labels[p] == -1:
                labels[p] = cluster_id  # border point, reclaim from noise
            if labels[p] != -2 and labels[p] != -1:
                continue
            labels[p] = cluster_id
            p_neighbors = np.where(distance[p] <= eps)[0]
            if len(p_neighbors) >= min_samples:
                for q in p_neighbors:
                    if labels[q] < 0:  # unvisited or noise → candidate seed
                        if q not in seeds:
                            seeds.append(int(q))
    return labels


def cluster_items(
    samples: list[tuple[str, dict]], eps: float = 0.6, min_samples: int = 2
) -> ClusterResult:
    """Cluster ``samples`` of (goods_name, tech_params) by name-text AND spec match.

    ``eps`` is the distance radius on the AND metric (see _pairwise_distance);
    items farther than ``eps`` from every cluster core (or in a cluster smaller
    than ``min_samples``) become noise (-1).
    """
    if not samples:
        return ClusterResult(labels=[], representatives={})

    vec = Vectorizer()  # fit 在 _pairwise_distance 内做(用剥规格后的纯名称)
    distance = _pairwise_distance(samples, vec)
    if distance.shape[0] == 0:
        return ClusterResult(labels=[], representatives={})

    labels = _dbscan(distance, eps, min_samples).tolist()

    reps: dict[int, str] = {}
    for label, (name, _) in zip(labels, samples):
        if label == -1:
            continue
        reps.setdefault(label, name)
    return ClusterResult(labels=labels, representatives=reps)
