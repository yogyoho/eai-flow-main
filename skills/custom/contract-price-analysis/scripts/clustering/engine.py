"""DBSCAN clustering over vectorized goods samples (numpy-only, no scikit-learn).

Density-based clustering on cosine distance. DBSCAN is chosen because the number
of distinct products is unknown and it explicitly marks outliers as noise (-1),
which surfaces anomalous prices for review rather than forcing them into a cluster.

Pure numpy: pairwise cosine distance matrix + a textbook DBSCAN expansion.
"""

from dataclasses import dataclass

import numpy as np

from scripts.clustering.vectorizer import Vectorizer


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
    """Cluster ``samples`` of (goods_name, tech_params) by cosine distance.

    ``eps`` is the cosine-distance radius; items farther than ``eps`` from every
    cluster core (or in a cluster smaller than ``min_samples``) become noise (-1).
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
