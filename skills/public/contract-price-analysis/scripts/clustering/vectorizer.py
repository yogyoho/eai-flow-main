"""Feature vectorizer: char-ngram TF-IDF over goods name text + spec token extraction.

Numpy-only implementation (no scikit-learn / scipy) so the pipeline runs in the
Gateway container without pulling the heavy scipy wheel. scikit-learn's TfidfVectorizer
is replaced by a compact char-wb (space-padded) n-gram TF-IDF; behavior is close
enough for goods-name similarity (the same "different writings of the same product
are close" property the tests rely on).

"同一商品" = 名称相似 **且** 规格匹配(v1 docstring 即此意图)。两个维度分开度量、
由 engine 取 min 做门限(AND),而不是拼进同一个余弦向量——加法语义会把"同名
不同商品的同规格对"或"同商品不同规格对"之一强行合并。
名称相似度: 本模块的 TF-IDF 余弦。
规格匹配度: spec_tokens() 抽取的规格 token 集合 Jaccard(engine 调用)。
"""

import re
from collections import Counter

import numpy as np

_NUM = re.compile(r"(\d+(?:\.\d+)?)")
# Canonical numeric tech-param fields (Chinese). Unrecognised keys are ignored.
_PARAM_FIELDS = ("电压", "电流", "容量", "功率", "频率", "压力", "温度", "流量", "转速", "扬程", "管径")

# 规格维度(Step 1, 细分需求): 不同规格 = 不同商品,必须分簇。v1 只处理 DN
# 管径;现泛化为 token 族——从样本文本抽取(spec_model 由 cli._cluster_sample_text
# 优先拼入),归一化后 one-hot: 不同 token 正交 → cosine=0 → 硬分离,同 token
# 加权聚拢。边沿用 (?<!..)/(?![0-9a-z]) 而非 \b:CJK 在 Python re 里是 \w,
# "管A108" 的 管-A 之间无 \b 边界。
_SPEC_TOKEN_RES: tuple[re.Pattern, ...] = (
    re.compile(r"DN\s*\d+(?:\.\d+)?", re.IGNORECASE),                # 管径 DN50
    re.compile(r"PN\s*=?\s*\d+(?:\.\d+)?", re.IGNORECASE),           # 压力等级 PN=1.60
    re.compile(r"[Φφ]\s*\d+(?:\.\d+)?"),                             # 直径 Φ12
    re.compile(r"\d+(?:\.\d+)?\s*mm", re.IGNORECASE),                # 厚度 20mm
    re.compile(r"(?<![A-Za-z0-9])Q\d{3}[A-Za-z]?(?![A-Za-z0-9])"),   # 钢牌号 Q235/Q355B
    re.compile(r"(?<![A-Za-z0-9])[A-Z]\d{3}(?![0-9A-Za-z])"),        # 无缝管牌号 A108
)


def _norm_spec(tok: str) -> str:
    """DN 50 / dn50 / PN = 1.60 → 同一 token。"""
    return re.sub(r"\s+", "", tok).upper()


def spec_extract(text: str) -> tuple[list[str], str]:
    """从样本文本抽取规格 token,并返回剥掉规格后的纯名称文本。

    剥离版供名称相似度使用: 否则"大理石 20mm"vs"人造石 20mm"的名称余弦
    会被共享的规格字符抬高(规格相似度有自己的 Jaccard 门限,不该重复计分)。
    剥完为空(名称本身纯规格,如"DN100")时调用方应回退原文。
    """
    toks: list[str] = []
    stripped = text
    for rx in _SPEC_TOKEN_RES:
        m = rx.search(stripped)
        if m:
            toks.append(_norm_spec(m.group(0)))
            stripped = stripped.replace(m.group(0), " ")
    return toks, re.sub(r"\s+", " ", stripped).strip()


def spec_tokens(text: str) -> list[str]:
    return spec_extract(text)[0]


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
        # 仅名称文本 TF-IDF。规格维度不再拼进同一向量:单余弦是加法语义,one-hot
        # 大权重会把"同名不同商品的同规格对"(大理石20mm vs 人造石20mm)强行合并。
        # 规格改由 engine 用 token Jaccard 做 AND 门限(见 engine._pairwise_distance)。
        return self._text_vector(goods_name)

    @staticmethod
    def _numval(text) -> float:
        m = _NUM.search(str(text))
        return float(m.group(1)) if m else 0.0
