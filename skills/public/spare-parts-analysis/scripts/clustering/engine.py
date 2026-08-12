# EAI-CUSTOM: forked from contract-price-analysis/scripts/clustering/engine.py(逐字)。
"""DBSCAN clustering over vectorized part samples (numpy-only, no scikit-learn)。

余弦距离上的密度聚类。选 DBSCAN 因为不同备件种数未知,且它显式把离群点标为噪声(-1),
从而把异常价格浮出来供复核,而不是硬塞进某个簇。纯 numpy:成对余弦距离矩阵 + 教科书
DBSCAN 扩展。cluster_id 写进 csp_items.cluster_id,是跨客户比价(D3)的连接键。
"""

from dataclasses import dataclass

import numpy as np

from scripts.clustering.vectorizer import Vectorizer


@dataclass
class ClusterResult:
    labels: list[int]  # -1 == noise / outlier
    representatives: dict[int, str]  # cluster label -> a representative part name


def _cosine_distance_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normalized = matrix / norms
    sim = normalized @ normalized.T
    return 1.0 - np.clip(sim, -1.0, 1.0)


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
    """Cluster ``samples`` of (part_name, tech_params) by cosine distance。

    ``eps`` 是余弦距离半径;离每个簇核都超过 ``eps`` 的项(或所在簇小于 ``min_samples``)
    成为噪声(-1),后续标为待人工归一。
    """
    if not samples:
        return ClusterResult(labels=[], representatives={})

    vec = Vectorizer().fit(samples)
    matrix = np.array([vec.transform(name, params) for name, params in samples])
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        return ClusterResult(labels=[], representatives={})

    distance = _cosine_distance_matrix(matrix)
    labels = _dbscan(distance, eps, min_samples).tolist()

    reps: dict[int, str] = {}
    for label, (name, _) in zip(labels, samples):
        if label == -1:
            continue
        reps.setdefault(label, name)
    return ClusterResult(labels=labels, representatives=reps)
