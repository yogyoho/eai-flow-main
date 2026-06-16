"""Feature vectorizer: char-ngram TF-IDF over goods name/spec + standardized tech params.

Numpy-only implementation (no scikit-learn / scipy) so the pipeline runs in the
Gateway container without pulling the heavy scipy wheel. scikit-learn's TfidfVectorizer
is replaced by a compact char-wb (space-padded) n-gram TF-IDF; behavior is close
enough for goods-name similarity (the same "different writings of the same product
are close" property the tests rely on).

The clustering feature is the concatenation of two parts so that two items are
considered "the same product" only when BOTH their textual description and their
key technical parameters match:

1. A char-ngram TF-IDF vector of the goods name.
2. A standardized numeric vector of extracted tech params.
"""

import re
from collections import Counter

import numpy as np

_NUM = re.compile(r"(\d+(?:\.\d+)?)")
# Canonical numeric tech-param fields (Chinese). Unrecognised keys are ignored.
_PARAM_FIELDS = ("电压", "电流", "容量", "功率", "频率", "压力", "温度", "流量", "转速", "扬程")


def _char_wb_ngrams(text: str, ngram_range: tuple[int, int]) -> list[str]:
    """Space-padded character n-grams in [lo, hi] (matches sklearn's char_wb)."""
    padded = " " + text + " "
    lo, hi = ngram_range
    grams: list[str] = []
    for n in range(lo, hi + 1):
        for i in range(len(padded) - n + 1):
            grams.append(padded[i : i + n])
    return grams


class Vectorizer:
    def __init__(self, ngram_range: tuple[int, int] = (2, 4)):
        self.ngram_range = ngram_range
        self._vocab: dict[str, int] = {}
        self._idf: np.ndarray | None = None
        self._param_keys: list[str] = []

    def fit(self, samples: list[tuple[str, dict]]) -> "Vectorizer":
        # Build vocabulary + document frequency over the goods names.
        df: Counter = Counter()
        doc_count = 0
        for name, _ in samples:
            grams = set(_char_wb_ngrams(name, self.ngram_range))
            for g in grams:
                df[g] += 1
            doc_count += 1
        self._vocab = {g: i for i, g in enumerate(sorted(df))}
        # idf = ln((1 + N) / (1 + df)) + 1  (sklearn smooth_idf default)
        n = len(self._vocab)
        self._idf = np.zeros(n, dtype=float)
        for g, i in self._vocab.items():
            self._idf[i] = np.log((1 + doc_count) / (1 + df[g])) + 1.0

        seen: set[str] = set()
        for _, params in samples:
            for k in params:
                if k in _PARAM_FIELDS:
                    seen.add(k)
        self._param_keys = sorted(seen)
        return self

    def _text_vector(self, name: str) -> np.ndarray:
        grams = _char_wb_ngrams(name, self.ngram_range)
        tf = np.zeros(len(self._vocab), dtype=float)
        for g in grams:
            idx = self._vocab.get(g)
            if idx is not None:
                tf[idx] += 1.0
        vec = tf * self._idf
        return vec

    def transform(self, goods_name: str, tech_params: dict) -> np.ndarray:
        text_vec = self._text_vector(goods_name)
        param_vec = np.array(
            [self._numval(tech_params.get(k, "0")) for k in self._param_keys],
            dtype=float,
        )
        if param_vec.size:
            std = param_vec.std()
            if std > 1e-9:
                param_vec = (param_vec - param_vec.mean()) / std
        return np.concatenate([text_vec, param_vec])

    @staticmethod
    def _numval(text) -> float:
        m = _NUM.search(str(text))
        return float(m.group(1)) if m else 0.0
