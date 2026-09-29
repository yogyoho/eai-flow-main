"""源③：schema-constrained LLM 因果链抽取（抽样 6-8 份，非全量）。

输入：fulltext .txt（4 份可用的）按章节切片；prompt 内嵌 v2 etype/谓词枚举 +
controlled_vocab aliases + 2 个 few-shot 金标准片段；输出候选 JSONL（不入图）。
env：EIA_MINING_LLM_BASE_URL / EIA_MINING_LLM_API_KEY / EIA_MINING_LLM_MODEL
     （OpenAI 兼容 chat/completions；值取自主系统 config.yaml 当前模型配置，人工填入）
用法：python llm_extract.py --src .wolf/tmp/eia-samples --samples samples.json --out out/llm_candidates.jsonl
（在 scripts/eia_schema_mining/ 目录内运行——controlled_vocab.yaml/samples.json 按相对路径读取）

⛔GATE（Task 6 Step 2）：samples.json 抽样清单待用户确认后才可运行本脚本；
用户可能提供更多已解析全文，届时扩充 reports 列表。当前为 Step 1 代码就位 + 占位清单。

语料文件名现实（与 table_extract.py 同核查）：3 份 `{slug}-fulltext.txt` +
1 份无前缀 `fulltext.txt`（高头窑矿区总体规划修编环评 → slug gaotaoyao），
resolve_fulltext 对无前缀全文做兜底解析。
"""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

CHUNK_CHARS = 8000  # ~4k 中文 token，句子级抽取粒度
SYSTEM = (
    "你是环评本体抽取器。从给定环评报告片段中抽取业务逻辑三元组。"
    "只输出 JSON 数组，每项 {subject, subject_type, predicate, object, object_type, evidence_quote}。"
    "subject_type/object_type 只能用【类型枚举】中的词，predicate 只能用【谓词枚举】中的词，"
    "禁止自造任何类型或谓词名；evidence_quote 必须逐字复制原文连续片段（≤80字，"
    "不得增删改字、不得用省略号拼接两处原文）；禁止复用示例中的三元组；没有把握的不要输出。"
)

_DRAFT = Path(__file__).resolve().parents[2] / "app" / "ontology" / "registry" / "eia.yaml"


def load_enums(source: Path = _DRAFT) -> str:
    """从正式 registry 抽枚举 + 中文标注（eia.yaml 注释块=唯一真源，杜绝 prompt 漂移）。

    要求用户规则：本体模型所有英文都要有对应中文——标注块缺失的枚举值裸输出，
    抽取质量归因时先查标注覆盖。
    """
    import re
    text = source.read_text(encoding="utf-8")
    labels: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"# (?:etype|谓词)中文标注: (.+)", line.strip())
        if m:
            for pair in m.group(1).split():
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    labels[k] = v

    def enum_line(key: str, label: str) -> str:
        m = re.search(re.escape(key) + r".*?enum: \[([^\]]+)\]", text)
        if not m:
            return f"【{label}】(missing in {source.name})"
        items = [v.strip() for v in m.group(1).split(",")]
        return f"【{label}】" + ", ".join(f"{v}({labels[v]})" if v in labels else v for v in items)

    return enum_line("name: etype,", "类型枚举") + "\n" + enum_line("name: predicate,", "谓词枚举")


def resolve_fulltext(src: Path, slug: str) -> Path | None:
    """slug → fulltext 文件。先认 {slug}-fulltext.txt，无前缀 fulltext.txt 兜底（语料唯一，=gaotaoyao）。"""
    cand = src / f"{slug}-fulltext.txt"
    if cand.exists():
        return cand
    bare = src / "fulltext.txt"
    return bare if bare.exists() else None


def build_user_prompt(chunk: str, vocab_digest: str, fewshots: str, enums: str) -> str:
    return f"{enums}\n\n### 同义词归一（抽取时统一到规范名）\n{fewshots}\n\n### 报告片段\n{chunk}\n\n只输出 JSON 数组。"


def extract_chunk(client: httpx.Client, chunk: str, vocab_digest: str, fewshots: str, enums: str = "",
                  attempts: int = 3) -> list[dict]:
    """单 chunk 抽取；超时与 5xx/429 瞬时错误重试（指数退避），非瞬时 4xx 直接炸出暴露配置问题。"""
    timeout = float(os.environ.get("EIA_MINING_LLM_TIMEOUT", "600"))
    for k in range(attempts):
        try:
            resp = client.post(
                "/chat/completions",
                json={
                    "model": os.environ["EIA_MINING_LLM_MODEL"],
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": build_user_prompt(chunk, vocab_digest, fewshots, enums)},
                    ],
                    "temperature": 0,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            break
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.TransportError):
            # TransportError 兜底 ConnectError(域名解析失败/网络抖动) 等全部传输层瞬时错误
            if k == attempts - 1:
                print("  chunk failed after retry, skipped", flush=True)
                return []
            time.sleep(5 * (k + 1))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (429, 500, 502, 503, 504):
                raise
            if k == attempts - 1:
                print(f"  chunk HTTP {exc.response.status_code} after retry, skipped", flush=True)
                return []
            time.sleep(10 * (k + 1))
    text = resp.json()["choices"][0]["message"]["content"]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        return []
    try:
        items = json.loads(text[start: end + 1])
    except json.JSONDecodeError:
        return []
    return [it for it in items if isinstance(it, dict) and {"subject", "predicate", "object"} <= set(it)]


def existing_spans(out_path: Path) -> dict[str, set[int]]:
    """断点续跑：读已有产物的每报告 chunk 起点（span[0]）覆盖集。"""
    spans: dict[str, set[int]] = {}
    if not out_path.exists():
        return spans
    for line in out_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            spans.setdefault(r["report"], set()).add(r["span"][0])
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
    return spans


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".wolf/tmp/eia-samples")
    ap.add_argument("--samples", default="samples.json")
    ap.add_argument("--out", default="out/llm_candidates.jsonl")
    ap.add_argument("--stride", type=int, default=1,
                    help="chunk 步长采样：2=隔一取一（schema 挖掘统计够用；逐 chunk 全量属子项目 2）")
    ap.add_argument("--workers", type=int, default=6, help="并发请求数")
    args = ap.parse_args()
    from coal_terms import COAL_TERMS  # noqa: F401  # 确保词典可导入
    enums = load_enums()
    vocab_digest = Path("controlled_vocab.yaml").read_text(encoding="utf-8")[:2000]
    fewshots = json.dumps([
        {"subject": "矿井涌水", "subject_type": "pollution_source", "predicate": "treated_by",
         "object": "矿井水处理站", "object_type": "treatment_measure",
         "evidence_quote": "矿井涌水经井下水处理站混凝沉淀处理后回用"},
        {"subject": "采煤工作面", "subject_type": "working_face", "predicate": "causes",
         "object": "地表沉陷预测", "object_type": "impact_result",
         "evidence_quote": "采用概率积分法预测首采区工作面开采后地表最大下沉值"},
    ], ensure_ascii=False)
    samples = json.loads(Path(args.samples).read_text(encoding="utf-8"))
    client = httpx.Client(base_url=os.environ["EIA_MINING_LLM_BASE_URL"],
                          headers={"Authorization": f"Bearer {os.environ['EIA_MINING_LLM_API_KEY']}"})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    src = Path(args.src)
    have = existing_spans(out)
    with out.open("a", encoding="utf-8") as fh:  # 断点续跑：追加模式
        for slug in samples["reports"]:
            txt = resolve_fulltext(src, slug)
            if txt is None:
                print(f"skip {slug}: no fulltext", flush=True)
                continue
            text = txt.read_text(encoding="utf-8", errors="ignore")
            spans = list(range(0, len(text), CHUNK_CHARS * args.stride))
            todo = [i for i in spans if i not in have.get(slug, set())]
            if not todo:
                print(f"skip {slug}: {len(spans)} chunks 已全部完成（断点续跑）", flush=True)
                continue
            total = len(spans)
            if len(todo) < total:
                print(f"resume {slug}: {len(todo)}/{total} chunks 缺失，续跑", flush=True)

            def job(i: int) -> tuple[int, list[dict]]:
                return i, extract_chunk(client, text[i: i + CHUNK_CHARS], vocab_digest, fewshots, enums)

            done = 0
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                for i, items in ex.map(job, todo):
                    done += 1
                    for item in items:
                        fh.write(json.dumps({"report": slug, "span": [i, i + CHUNK_CHARS], **item},
                                            ensure_ascii=False) + "\n")
                    if done % 20 == 0:
                        print(f"{slug}: {done}/{len(todo)} chunks", flush=True)
            print(f"done {slug}: {len(todo)}/{total} chunks", flush=True)
            fh.flush()
    print(f"→ {out}")


if __name__ == "__main__":
    main()
