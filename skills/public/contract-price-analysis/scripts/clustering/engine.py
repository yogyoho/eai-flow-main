"""DBSCAN clustering over vectorized goods samples (numpy-only, no scikit-learn).

Density-based clustering on cosine distance. DBSCAN is chosen because the number
of distinct products is unknown and it explicitly marks outliers as noise (-1),
which surfaces anomalous prices for review rather than forcing them into a cluster.

Pure numpy: pairwise cosine distance matrix + a textbook DBSCAN expansion.
"""

from dataclasses import dataclass
import re

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


def _category_similarity(a: str, b: str) -> float:
    """类目门限(设计 §1.3"同名不同分类必须分簇")。

    双方有类目: 归一化(去空白,OCR 常拆字)相等=1.0,不同=0.0(硬分离);
    任一方缺失=1.0 中性(分类抽取噪声大,不惩罚提取缺口)。
    类目绝不进文本向量——短货名会被同分类长字符串淹没(真机 81 条 mega 簇案例)。
    """
    na, nb = re.sub(r"\s+", "", a or ""), re.sub(r"\s+", "", b or "")
    if not na or not nb:
        return 1.0
    return 1.0 if na == nb else 0.0


def _pairwise_distance(
    samples: list[tuple[str, dict]],
    vec: Vectorizer,
    use_spec: bool = True,
    use_category: bool = True,
) -> np.ndarray:
    """"同一商品" = 名称相似 **且** 规格匹配 **且** 类目一致
    → d = max(名称余弦距离, 规格Jaccard距离, 类目距离)。

    use_spec/use_category=False → 对应门限中性放行(设置页分组开关)。
    名称相似度在剥掉规格 token 的纯名称上计算(规格有独立门限,不重复计分);
    剥完为空的名称回退原文。min(相似度) 的 AND 语义: 任一启用维度不达标即分离。
    ponytail: O(n²) 纯 python Jaccard,504 行 <2s,真慢了再换稀疏矩阵。
    """
    n = len(samples)
    name_texts: list[str] = []
    tok_sets: list[set[str]] = []
    cats: list[str] = []
    for (name, params), (toks, stripped) in zip(samples, [spec_extract(x[0]) for x in samples]):
        name_texts.append(stripped or name)  # 剥完为空(名称纯规格)回退原文
        tok_sets.append(set(toks))
        cat = params.get("category") if isinstance(params, dict) else None
        cats.append(cat or "")
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
            spec_d = 1.0 - _spec_similarity(tok_sets[i], tok_sets[j]) if use_spec else 0.0
            cat_d = 1.0 - _category_similarity(cats[i], cats[j]) if use_category else 0.0
            dist[i, j] = max(text_d[i, j], spec_d, cat_d)
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


def _apply_merge_pins(
    labels: list[int],
    name_ids: list[set[str]] | list[str],
    pins: list[dict],
    spec_sets: list[frozenset] | None = None,
) -> list[int]:
    """合并先验重放: 名称命中任一 pin(name/aliases, 归一化去空白)的样本所属簇
    强制并为一簇(并查集); 落单变体也吸收进组。pin 在统计/离群推导之前生效,
    合并簇的全链路派生值自洽。误合并通过删除术语/pin 条目撤销。

    name_ids: 每样本的归一化名身份——str(旧语义,单名)或 set(全名+剥规格名双身份:
    术语表裸名走剥规格身份,手动合并捕获的带规格 pin 走全名身份)。
    spec_sets: 每样本规格 token frozenset; 提供时 pin 命中后按规格分组再并——
    同名**同规格**才并(∅ 只并 ∅)。EAI-CUSTOM(2026-10-22): 螺纹钢 26 规格错簇
    根因 = 剥规格匹配把不同规格的同名行全部强制并簇,击穿规格 AND 门;术语的
    职责是并「名称变体」而非「规格家族」,规格区分永远交给规格门。"""
    parent = list(range(len(labels)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # 同簇天然同根; 跨簇按 pin 归并
    by_root: dict[int, list[int]] = {}
    for i, lb in enumerate(labels):
        if lb != -1:
            by_root.setdefault(lb, []).append(i)
    for members in by_root.values():
        for i in members[1:]:
            union(members[0], i)

    for pin in pins or []:
        wanted = {
            re.sub(r"\s+", "", str(n or "")) for n in [pin.get("name"), *(pin.get("aliases") or [])]
        } - {""}
        if not wanted:
            continue
        idxs = [
            i
            for i, ids in enumerate(name_ids)
            if (ids in wanted if isinstance(ids, str) else bool(ids & wanted))
        ]
        if spec_sets is None:
            for i in idxs[1:]:
                union(idxs[0], i)
        else:
            # 同名同规格才并(∅ 只并 ∅)——按 token 分组后组内并查
            by_spec: dict[frozenset, list[int]] = {}
            for i in idxs:
                by_spec.setdefault(spec_sets[i], []).append(i)
            for members in by_spec.values():
                for i in members[1:]:
                    union(members[0], i)

    # 根 → 代表 label(组内最小正 label; 全负则保持 -1)
    root_label: dict[int, int] = {}
    for i, lb in enumerate(labels):
        r = find(i)
        if lb != -1 and (r not in root_label or (0 <= root_label[r] > lb)):
            root_label[r] = lb
    return [root_label.get(find(i), -1) for i in range(len(labels))]


def cluster_items(
    samples: list[tuple[str, dict]],
    eps: float = 0.6,
    min_samples: int = 2,
    use_spec: bool = True,
    use_category: bool = True,
    merge_pins: list[dict] | None = None,
    split_rules: list[dict] | None = None,
) -> ClusterResult:
    """Cluster ``samples`` of (goods_name, tech_params) by name-text AND spec match.

    ``eps`` is the distance radius on the AND metric (see _pairwise_distance);
    items farther than ``eps`` from every cluster core (or in a cluster smaller
    than ``min_samples``) become noise (-1). use_spec/use_category 关断对应
    AND 门限(False → 该维中性放行,退化为名称单维)——设置页"货物分组规则"
    checkbox 的管线入口;名称恒开(UI 锁定)。merge_pins 为人工合并先验
    ([{name, aliases}]),DBSCAN 后强制归并命中簇(见 _apply_merge_pins)。
    split_rules 为易混名称区分规则([{name_a, name_b}],EAI-CUSTOM 2026-10-22):
    命中对在距离矩阵注入 1.0(斩断 DBSCAN 直连),落簇后再强制分离(斩断桥接
    链)——区分优先于归并(split 在 pin 之后执行,同对两表皆命中时区分赢)。"""
    if not samples:
        return ClusterResult(labels=[], representatives={})

    # 双身份(全名+剥规格名)与规格集: pins/splits 共用,任一存在即计算
    name_ids: list[set[str]] = []
    spec_sets: list[frozenset] = []
    if merge_pins or split_rules:
        for name, _ in samples:
            toks, stripped = spec_extract(name)
            name_ids.append({re.sub(r"\s+", "", name), re.sub(r"\s+", "", stripped or name)})
            spec_sets.append(frozenset(toks))

    vec = Vectorizer()  # fit 在 _pairwise_distance 内做(用剥规格后的纯名称)
    distance = _pairwise_distance(samples, vec, use_spec=use_spec, use_category=use_category)
    if distance.shape[0] == 0:
        return ClusterResult(labels=[], representatives={})

    # 区分规则①距离注入: 命中对距离=1.0,斩断 DBSCAN 直连边
    for rule in split_rules or []:
        a_ids = {re.sub(r"\s+", "", str(rule.get("name_a") or ""))}
        b_ids = {re.sub(r"\s+", "", str(rule.get("name_b") or ""))}
        if not a_ids - {""} or not b_ids - {""}:
            continue
        a_idx = [i for i, ids in enumerate(name_ids) if ids & a_ids]
        b_idx = [i for i, ids in enumerate(name_ids) if ids & b_ids]
        for i in a_idx:
            for j in b_idx:
                if i != j:
                    distance[i, j] = distance[j, i] = 1.0

    labels = _dbscan(distance, eps, min_samples).tolist()
    if merge_pins:
        # 双身份匹配: 全名(手动合并捕获的带规格 pin,如「热镀锌无缝钢管 DN32」)
        # + 剥规格名(术语表裸名,如「螺纹钢」);spec_sets 供分组并查(同名同规格
        # 才并,∅ 只并 ∅——2026-10-22 螺纹钢 26 规格错簇修复)。
        labels = _apply_merge_pins(labels, name_ids, merge_pins, spec_sets)

    # 区分规则②落簇后强制分离: 桥接链(管内穿线~共性桥名~桥架内穿线)绕过距离
    # 注入时,同簇的 B 侧成员整体迁出到新 label——区分赢过一切归并路径。
    for rule in split_rules or []:
        a_ids = {re.sub(r"\s+", "", str(rule.get("name_a") or ""))}
        b_ids = {re.sub(r"\s+", "", str(rule.get("name_b") or ""))}
        if not a_ids - {""} or not b_ids - {""}:
            continue
        a_idx = [i for i, ids in enumerate(name_ids) if ids & a_ids]
        b_idx = [i for i, ids in enumerate(name_ids) if ids & b_ids]
        shared = {labels[i] for i in a_idx if labels[i] != -1} & {labels[j] for j in b_idx if labels[j] != -1}
        for lb in shared:
            next_label = max(l for l in labels if l >= 0) + 1 if any(l >= 0 for l in labels) else 0
            for j in b_idx:
                if labels[j] == lb:
                    labels[j] = next_label

    reps: dict[int, str] = {}
    for label, (name, _) in zip(labels, samples):
        if label == -1:
            continue
        reps.setdefault(label, name)
    return ClusterResult(labels=labels, representatives=reps)
