# EAI-CUSTOM: forked from contract-price-analysis/scripts/clustering/vectorizer.py(逐字)。
# _PARAM_FIELDS(电压/电流/容量/功率/频率/压力/温度/流量/转速/扬程/管径)是通用工业参数,
# 已覆盖备件域(轴承→转速,阀门→压力/管径,电机→电压/功率,密封件→温度/压力),无需改。
"""Feature vectorizer: char-ngram TF-IDF over part name/spec + standardized tech params。

Numpy-only(no scikit-learn / scipy),管线在 Gateway 容器里跑无需拉重 wheel。scikit-learn
的 TfidfVectorizer 用紧凑 char-wb(空格填充)n-gram TF-IDF 替代;对备件名相似度行为够用
(测试依赖的"同一零件的不同写法彼此接近"性质不变)。

聚类特征 = 两部分拼接,使两件备件只在文本描述 AND 关键技术参数都匹配时才判为"同一零件":
  1. 备件名的 char-ngram TF-IDF 向量;
  2. 抽出的技术参数的标准化数值向量(DN 管径做 one-hot,不同 DN = 不同件)。
"""

import re
from collections import Counter

import numpy as np

_NUM = re.compile(r"(\d+(?:\.\d+)?)")
# Canonical numeric tech-param fields (Chinese). Unrecognised keys are ignored.
_PARAM_FIELDS = ("电压", "电流", "容量", "功率", "频率", "压力", "温度", "流量", "转速", "扬程", "管径")

_DN_RE = re.compile(r"DN\s*(\d+)", re.IGNORECASE)


def _char_wb_ngrams(text: str, ngram_range: tuple[int, int]) -> list[str]:
    """Space-padded character n-grams in [lo, hi] (matches sklearn's char_wb)。"""
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
        self._dn_values: list[str] = []  # unique DN values for one-hot encoding

    def fit(self, samples: list[tuple[str, dict]]) -> "Vectorizer":
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
        # Collect unique DN values for one-hot encoding (different DN sizes =
        # different parts, must not cluster together).
        dn_set: set[str] = set()
        for name, _ in samples:
            for m in _DN_RE.finditer(name):
                dn_set.add(m.group(1))
        self._dn_values = sorted(dn_set)
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

    def transform(self, part_name: str, tech_params: dict) -> np.ndarray:
        text_vec = self._text_vector(part_name)
        # Normalize text to unit length so DN one-hot isn't drowned out.
        text_norm = np.linalg.norm(text_vec)
        if text_norm > 1e-9:
            text_vec = text_vec / text_norm
        # DN one-hot: different DN sizes are orthogonal → cosine = 0 → separated.
        # param_vec dropped — its raw values (40/50/100) dominated cosine and
        # per-sample standardization (std=0 for 1-dim) was a no-op. The DN
        # one-hot fully handles DN distinction.
        dn_vec = np.zeros(max(len(self._dn_values), 1), dtype=float)
        dn_match = _DN_RE.search(part_name)
        if dn_match and dn_match.group(1) in self._dn_values:
            dn_vec[self._dn_values.index(dn_match.group(1))] = 1.0
        DN_WEIGHT = 5.0
        return np.concatenate([text_vec, dn_vec * DN_WEIGHT])

    @staticmethod
    def _numval(text) -> float:
        m = _NUM.search(str(text))
        return float(m.group(1)) if m else 0.0
