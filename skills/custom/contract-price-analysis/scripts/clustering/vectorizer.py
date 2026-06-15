"""Feature vectorizer: TF-IDF over goods name/spec + standardized tech params.

The clustering feature is the concatenation of two parts so that two items are
considered "the same product" only when BOTH their textual description and their
key technical parameters match:

1. A char-ngram TF-IDF vector of the goods name (+ spec). Char ngrams are robust
   to the many ways the same product is written (e.g. "高压开关柜" vs
   "10kV高压开关柜").
2. A standardized numeric vector of extracted tech params (电压/电流/容量/...).
   Standardization (z-score) keeps wildly different parameter scales (kV vs kVA)
   comparable and prevents one dimension from dominating.

Without the param part, "高压开关柜" at 10kV and at 35kV would collapse into one
cluster and produce a meaningless average price.
"""

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

_NUM = re.compile(r"(\d+(?:\.\d+)?)")
# Map a tech-param dict key (Chinese) to a canonical numeric field. Unrecognised
# keys are ignored so they don't pollute the numeric vector.
_PARAM_FIELDS = ("电压", "电流", "容量", "功率", "频率", "压力", "温度", "流量", "转速", "扬程")


class Vectorizer:
    def __init__(self):
        self._text = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self._param_keys: list[str] = []

    def fit(self, samples: list[tuple[str, dict]]) -> "Vectorizer":
        texts = [name for name, _ in samples]
        self._text.fit(texts)
        # Union of all param keys seen, restricted to known canonical fields.
        seen = set()
        for _, params in samples:
            for k in params:
                if k in _PARAM_FIELDS:
                    seen.add(k)
        self._param_keys = sorted(seen)
        return self

    def transform(self, goods_name: str, tech_params: dict) -> np.ndarray:
        text_vec = self._text.transform([goods_name]).toarray()[0]
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
