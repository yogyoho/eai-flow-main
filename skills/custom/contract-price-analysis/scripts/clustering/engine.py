"""DBSCAN clustering over vectorized goods samples.

DBSCAN is chosen over KMeans because:
- The number of distinct products is unknown (KMeans needs a preset K).
- It explicitly marks outliers as noise (label -1), which surfaces anomalous
  prices for human review rather than forcing them into a cluster.

The cosine metric is used on L2-normalized vectors so the cluster decision is
based on direction (semantic + param similarity), not magnitude.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import normalize

from scripts.clustering.vectorizer import Vectorizer


@dataclass
class ClusterResult:
    labels: list[int]  # -1 == noise / outlier
    representatives: dict[int, str]  # cluster label -> a representative goods name


def cluster_items(
    samples: list[tuple[str, dict]], eps: float = 0.6, min_samples: int = 2
) -> ClusterResult:
    """Cluster ``samples`` of (goods_name, tech_params).

    ``eps`` is the cosine-distance radius; items farther than ``eps`` from every
    cluster core (or in a cluster smaller than ``min_samples``) become noise (-1).
    """
    if not samples:
        return ClusterResult(labels=[], representatives={})

    vec = Vectorizer().fit(samples)
    matrix = np.array([vec.transform(name, params) for name, params in samples])
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        return ClusterResult(labels=[], representatives={})

    normalized = normalize(matrix)
    db = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit(normalized)
    labels = db.labels_.tolist()

    reps: dict[int, str] = {}
    for label, (name, _) in zip(labels, samples):
        if label == -1:
            continue
        reps.setdefault(label, name)
    return ClusterResult(labels=labels, representatives=reps)
