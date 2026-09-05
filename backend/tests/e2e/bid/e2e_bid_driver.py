"""bid-proposal-writing E2E 压测驱动(bug-2189 转正版; host 侧 stdlib-only, 不进 pytest 默认收集)。

用法(独立入口, 不依赖 pytest/CI; 需要活网关 http://localhost:2026):
    python backend/tests/e2e/bid/e2e_bid_driver.py                     # 全新线程+默认 fixture(minimal_tender.docx)
    python backend/tests/e2e/bid/e2e_bid_driver.py --upload <招标.pdf> --model agnes-2.5-Flash
    python backend/tests/e2e/bid/e2e_bid_driver.py --resume <tid> --resume-start 8 --resume-msg <续作指令>
跑完用同目录 score_checkpoints.py 打 CP1-CP6 分。

流程: login -> 线程(create+upload 或 resume) -> 脚本化多轮流式 run(确认门1/2 自动应答)
-> 进度日志。日志(OUT, 默认 backend/.deer-flow/e2e_bid/): e2e_progress.log + e2e_turn{N}.sse(原始帧)。

== RED 基线(bug-2189 E2E 实录, 2026-08-20, agnes-2.5-Flash, 江西师大真实 PDF, 线程 bbd447d7, 8 轮到交付) ==
验收口径 = 违规轮次 0 且特征实例 0(双轨都过, 铁律9=禁止任何途径直写 state/):
- 违规轮次 = 3(turn2/7/8); 特征写实例 = 5+(turn8 独占 4 次)。
  注: 这组数字出自 RED 年代的 grep 版评分器, 与现行评分器重放不逐位可比, 只作量级对照。
  现行 CP5 重放(bug-3032 收紧后)实测: agnes_fixed 语料(驱动修复前, thread 6eb0a8ba)
  = 6 违规轮(turn1-5,9)/15 实例, 全部 bash py-write 直写 state; 旧全文扫描曾计的
  turn7 2×str_replace(project_snapshot.json, workspace 根, 非 state/)在 path 字段
  口径下不再计——手写快照+辅助脚本绕行属已记录残余盲区, 由 CP6 签名+WP-B 新鲜度兜底。
转正版在此基线上复跑: agnes 基线须不退步, 生产级模型复测做 CP2/CP3 归因。

bug-2204 加固(实录沉淀, 保留):
- interrupt 检测走 values 帧 __interrupt__ 键(序列化契约; SSE event=__interrupt__ 在本网关不发)
- StreamGap 韧性: event: gap / 无 end 帧 EOF -> 从留存尾 join 回 run SSE 直到终态;
  被取消的 run 自动补一轮 "continue"(checkpointer 保状态)

bug-2210 (2026-08-30, 网关平台契约变化): ask_clarification 不再序列化为 __interrupt__
(run success 收尾, checkpoint 无中断键) —— 模型软暂停等下一条用户消息。driver 检测
"干净结束 + 见过 ask_clarification" 即视为确认门暂停, 以 last_ai 为问题文本走 ANSWERS 表。
变体: 模型偶尔连 ask_clarification 都不调, 直接以确认门措辞(确认门/待用户确认/请确认/
待确认)的纯文本收尾 —— 同样视为软暂停。

bug-3037 (2026-08-30, 门轮空转停滞): 软暂停自动应答可能陷入"复述完成状态+门措辞 ->
罐头确认 -> 再复述"死循环(干净复跑实录 turn14-22 连续 9 轮 tools(0), 烧 ~25min)。
stall_step 以"工具窗口无新工具名"为无进展信号: 连续 STALL_N 轮 -> 投一次终结指令
(两条出路: 继续执行 / present_files 收口); 升级后仍无进展 -> 停机。不设链内
present_files 直判完成——它是中段门工件信号, 完成判定只归 COMPLETION_RECAP
(对抗评审 wgu46e22u blocker)。
"""

import argparse
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar
from pathlib import Path

# Windows detached launch redirects stdout/stderr through the default GBK codec;
# model text (¥, mojibake) then kills the driver with UnicodeEncodeError mid-run.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:2026"
REPO = Path(__file__).resolve().parents[3]  # backend/
DEFAULT_UPLOAD = REPO / "tests" / "fixtures" / "bid_proposal" / "minimal_tender.docx"
DEFAULT_OUT = REPO / ".deer-flow" / "e2e_bid"

T1 = "请使用 bid-proposal-writing 技能处理我上传的招标文件(严格按 SKILL.md 六阶段流程生成投标方案: 技术响应三模式供源, 不做 Word 转换)。"

RECURSION_RETRY_MSG = "上一轮因递归预算耗尽被中断, 状态已保留。请从中断处继续执行当前阶段, 不要重做已完成的步骤。"
CANCEL_RETRY_MSG = "上一轮流连接中断被取消, 状态已保留。请从中断处继续执行当前阶段, 不要重做已完成的步骤。"
TOOL_LIMIT_CONTINUE_MSG = "上一轮因单工具调用次数上限被截断, 状态已保留。请从中断处继续执行当前阶段, 不要重做已完成的步骤。提示: 对成批的同构操作(如逐个验证候选文件)请用一次 bash 循环批量完成, 减少单工具调用次数。"

# 确认门自动应答表(问题文本含关键词即答; 最后一项兜底)。--answers JSON 可整体替换。
# 行序即匹配优先级(bug-3032): 确认门2 逐字模板含"新实体确认列", 实体 必须排在
# 补遗/终稿 之后, 否则门2 被答成门1 的白名单锁定(实测 4 连空转诱导 str_replace)。
ANSWERS = [
    ("分类", "分类全部确认无误; 实体白名单按你提取的结果确认锁定; 请继续后续阶段。"),
    ("补遗", "补遗合并 diff 表逐项确认无误; 新实体确认列确认锁定; 终稿复核清单逐项通过; 如有待裁决 mapping_id, 对无异议项按 apply 处理并报我有异议项; 请继续交付六件套并进阶段5。"),
    ("终稿", "终稿复核清单逐项通过, 请继续交付六件套并进阶段5。"),
    ("实体", "实体白名单确认锁定, 请继续。"),
    ("未裁决", "对未裁决项请按既定裁决规则处理(默认判空并记录), 完成全部 chunk/table 裁决后执行 extract merge, 再按流程继续。不要跳过评分细则表。"),
    ("样例", "没有参考样例文件可上传, 请按模式3用 web_search 深度编写技术响应。"),
    ("确认", "确认, 请继续。"),
]

# PREMATURE_STOP 哨兵: 轮末干净结束但无门/交付证据时 interrupt_q 用它占位,
# 绝不把 last_ai 喂给 pick_answer(bug-3032)——否则状态通报里的"分类/实体"字样
# 会触发确认门罐头答案, 在被测管线中途注入伪造的用户确认。
PREMATURE = "<<PREMATURE_STOP>>"
# 中性续作指令: 不确认任何门、不预设任何阶段状态, 只要求继续。
PREMATURE_CONTINUE_MSG = "请从上一步中断处继续执行当前阶段, 不要重做已完成的步骤。若当前阶段已完成, 请按 SKILL.md 流程进入下一阶段; 若在等待用户确认, 请用 ask_clarification 明确列出待确认项。"
# bug-3037 停滞升级指令: 门轮空转(复述状态+门措辞, 无新工具进展)达到阈值后投一次,
# 给模型两条正经出路(收口交付 或 列明阻塞), 打断"复述->罐头确认->复述"循环。
STALL_TERMINATE_MSG = "若管线尚未完成: 请继续执行当前阶段, 不要等待确认; 若确已全部完成: 请调用 present_files 交付成果并结束回复。不要再复述已报送过的状态或确认请求。"
# 供应商级失败(402/超时等被归一化为助手文本)特征——不再续推死 key(bug-3032)。
TERMINAL_AI_ERR_RE = re.compile(r"LLM request failed|Error code: 4\d\d")

CONTENT_TYPES = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".md": "text/markdown"}

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
OUT = DEFAULT_OUT
BASE_URL = BASE
MODEL = "agnes-2.5-Flash"
UPLOAD = DEFAULT_UPLOAD


def csrf() -> str:
    for c in jar:
        if c.name == "csrf_token":
            return c.value
    return ""


def post_json(path, payload, timeout=120):
    req = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf()},
        method="POST",
    )
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_json(path, timeout=120):
    req = urllib.request.Request(BASE_URL + path, headers={"X-CSRF-Token": csrf()})
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(OUT / "e2e_progress.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def wait_healthy(timeout=600):
    """Block until the gateway answers /health 200 (survives 502 windows)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE_URL + "/health", timeout=10) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False


def login():
    post_json("/api/extensions/auth/login", {"username": "admin@eai-flow.com", "password": "Admin@2026"})
    log(f"login ok, cookies={[c.name for c in jar]}")


def upload(tid):
    boundary = uuid.uuid4().hex
    fn = UPLOAD.name.encode("utf-8")
    ctype = CONTENT_TYPES.get(UPLOAD.suffix.lower(), "application/octet-stream")
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="files"; filename="' + fn + b'"\r\n',
            f"Content-Type: {ctype}\r\n\r\n".encode(),
            UPLOAD.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    req = urllib.request.Request(
        BASE_URL + f"/api/threads/{tid}/uploads",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf()},
        method="POST",
    )
    with opener.open(req, timeout=300) as r:
        log(f"upload: {r.status} {r.read().decode('utf-8')[:200]}")


def pick_answer(question):
    for key, ans in ANSWERS:
        if key in question:
            return ans
    return ANSWERS[-1][1]


STALL_N = 3  # bug-3037: 连续 N 个"无新工具进展"的门轮触发停滞处置


def stall_step(count, escalated, seen, tools, prev_tools):
    """bug-3037 门轮空转停滞判定(纯函数, 便于单测)。

    SOFT_GATE/SOFT_CLARIFICATION 自动应答路径每轮调用一次。工具窗口 = 本轮∪上轮
    工具名集合; 窗口内出现链内(seen)未见过的工具名 = 有新进展, 计数清零, 否则 +1。
    连续 STALL_N 轮无新进展: 未升级过 -> escalate(投一次 STALL_TERMINATE_MSG, 给
    模型两条正经出路: 继续执行 或 present_files 收口); 升级后仍无进展 -> abort 停机。
    不设"链内 present_files 直判完成": 本 skill 的确认门1/2 工件(条款清单/补遗diff表)
    也经 present_files 呈现, 链内出现过≠终稿已交付——完成判定只归 turn() 的
    COMPLETION_RECAP(当轮 markers+present_files)。证据直判会把门1 后任意 3 连无进展
    门轮误杀成半程"完成"(对抗评审 wgu46e22u blocker)。
    返回 (count, escalated, seen, action); action ∈ answer|escalate|abort。
    """
    window = set(tools) | set(prev_tools)
    new = window - seen
    seen = seen | window
    if new:
        count = 0
    else:
        count += 1
    if count < STALL_N:
        return count, escalated, seen, "answer"
    if not escalated:
        return 0, True, seen, "escalate"
    return count, escalated, seen, "abort"


class TurnState:
    def __init__(self):
        self.tools = []  # tool-name list (dedup later)
        self.ai_texts = {}  # message id -> accumulated AI text
        self.ai_order = []
        self.interrupt_q = None
        self.error = None
        # values 帧是全量历史快照(bug-3032): "[FORCED STOP]" 一旦发生, 后续每帧都含。
        # 存帧内出现次数, 轮末与上轮计数比差值——只有增量才说明本轮真被截断,
        # 否则历史回放会把 forced 标志永久粘住, 吃光续推预算。
        self.forced_count = 0
        self.llm_error = False  # deerflow_error_fallback 标记出现(供应商级失败)
        self.gap = False
        self.saw_end = False
        self.last_id = None


def _absorb_frame(event, data, st):
    """Fold one SSE frame's payload into the turn state."""
    if event == "end":
        st.saw_end = True
        return
    if event == "gap":
        st.gap = True
        try:
            g = json.loads(data) if data else {}
            st.last_id = g.get("latest_available_event_id") or st.last_id
            log(f"  gap: requested={g.get('requested_event_id')} latest={g.get('latest_available_event_id')} -> rejoin")
        except Exception:
            pass
        return
    if event == "error":
        st.error = data[:1000]
        return
    if event == "__interrupt__":
        try:
            obj = json.loads(data)
            iv = obj[0].get("value") if isinstance(obj, list) and obj and isinstance(obj[0], dict) else obj
            st.interrupt_q = iv if isinstance(iv, str) else json.dumps(iv, ensure_ascii=False)
        except Exception:
            st.interrupt_q = data[:800]
        return
    if event == "values":
        # giant frames at 88k ctx: substring pre-check before paying json.loads
        if "[FORCED STOP]" in data:
            st.forced_count = max(st.forced_count, data.count("[FORCED STOP]"))
        if '"__interrupt__"' not in data:
            if "deerflow_error_fallback" in data:
                st.llm_error = True
            return
        try:
            obj = json.loads(data)
        except Exception:
            return
        iv = obj.get("__interrupt__") if isinstance(obj, dict) else None
        if not iv:
            return
        first = iv[0] if isinstance(iv, list) and iv else iv
        val = first.get("value") if isinstance(first, dict) else first
        if val is None:
            return
        st.interrupt_q = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
        return
    if event == "messages":
        try:
            obj = json.loads(data)
        except Exception:
            return
        if not (isinstance(obj, list) and obj and isinstance(obj[0], dict)):
            return
        m = obj[0]
        for tc in m.get("tool_call_chunks") or []:
            if tc.get("name"):
                st.tools.append(tc["name"])
        mid = m.get("id")
        content = m.get("content")
        if mid and isinstance(content, str) and content:
            if mid not in st.ai_texts:
                st.ai_order.append(mid)
            st.ai_texts[mid] = st.ai_texts.get(mid, "") + content


def _read_sse(resp, raw, st):
    """Consume an SSE HTTP response into the turn state; returns at EOF."""
    event = ""
    for line_b in resp:
        line = line_b.decode("utf-8", "replace").rstrip("\n")
        raw.write(line + "\n")
        if line.startswith("id:"):
            _id = line[3:].strip()
            if _id:
                st.last_id = _id
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
            continue
        if not line.startswith("data:"):
            continue
        _absorb_frame(event, line[5:].strip(), st)


def latest_run(tid):
    runs = get_json(f"/api/threads/{tid}/runs")
    return runs[0] if runs else None


def _fetch_terminal_truth(tid, rid, st):
    """Run status is terminal — pull run.error truth from the event store."""
    try:
        evs = get_json(f"/api/threads/{tid}/runs/{rid}/events")
    except Exception as e:
        log(f"  events fetch failed: {e}")
        return
    for e in evs:
        if e.get("event_type") == "run.error":
            c = e.get("content") or ""
            et = (e.get("metadata") or {}).get("error_type", "?")
            st.error = f"{c[:400]} ({et})"


def turn(tid, n, message, with_files=False, prev_forced=0):
    """跑一轮流式 run。返回 (interrupt_q, last_ai, error, forced_now, forced_count, tools)。

    forced_now = 本轮新增的 loop-guard 截断(prev_forced 为上轮累计帧计数,
    差值>0 才算新截断——历史快照回放不算, bug-3032)。
    tools = 本轮去重后的工具名列表(bug-3037 空转停滞判定的进展信号)。
    """
    user_msg = {"role": "user", "content": message}
    if with_files:
        user_msg["additional_kwargs"] = {
            "files": [
                {
                    "filename": UPLOAD.name,
                    "size": UPLOAD.stat().st_size,
                    "path": f"/mnt/user-data/uploads/{UPLOAD.name}",
                    "status": "completed",
                }
            ]
        }
    payload = {
        "assistant_id": "lead_agent",
        "input": {"messages": [user_msg]},
        "config": {"recursion_limit": 1000},
        "context": {"model_name": MODEL, "thinking_enabled": False, "thread_id": tid},
        "stream_mode": ["messages-tuple", "values"],
    }
    req = urllib.request.Request(
        BASE_URL + f"/api/langgraph/threads/{tid}/runs/stream",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream", "X-CSRF-Token": csrf()},
        method="POST",
    )
    st = TurnState()
    # Self-healing POST: 502/URLError -> wait for gateway; 409 -> a run from a
    # previous (killed) driver is still active on this thread -> skip straight
    # to the recovery loop, which joins that run instead of creating a new one.
    for attempt in range(6):
        try:
            with opener.open(req, timeout=3600) as r, open(OUT / f"e2e_turn{n}.sse", "w", encoding="utf-8") as raw:
                try:
                    _read_sse(r, raw, st)
                except (OSError, http.client.HTTPException) as e:
                    # 流中途掉线(RST/1h socket 静默/chunked 截断, bug-3032): run 可能
                    # 仍在服务端执行——不当致命错, 落入下方 Last-Event-ID 回接恢复。
                    # 不能在此重新 POST: 旧 run 仍注册着, 409 attach 路径才是重入通道。
                    log(f"  turn{n}: stream dropped mid-run ({type(e).__name__}: {e}); entering recovery")
            break
        except urllib.error.HTTPError as e:
            if e.code == 409:
                log(f"  turn{n}: run already active on thread -> attach via join")
                break
            log(f"  turn{n}: HTTP {e.code}; waiting for gateway")
            wait_healthy()
            time.sleep(3)
        except urllib.error.URLError as e:
            log(f"  turn{n}: conn err {e.reason}; waiting for gateway")
            wait_healthy()
            time.sleep(3)
        except OSError as e:
            # POST 阶段的裸连接错(连接重置等, 非 URLError 包装); HTTPError/URLError
            # 已在上面分支处理, 这里兜住剩余 OSError 走同一恢复路径
            log(f"  turn{n}: conn err {e}; waiting for gateway")
            wait_healthy()
            time.sleep(3)
    else:
        log(f"  turn{n}: cannot reach gateway after retries")
        return None, "", "gateway_unreachable", False, 0, []

    # bug-2204 gap resilience: stream ended without end-frame while the run may
    # still be alive (StreamGap kick / connection drop). Re-join at the retained
    # tail until the run is terminal, then read error truth from the event store.
    rejoins = 0
    while not st.saw_end and st.interrupt_q is None and st.error is None and rejoins < 60:
        rejoins += 1
        try:
            rec = latest_run(tid)
        except Exception as e:
            log(f"  status poll failed: {e}")
            time.sleep(3)
            continue
        if not rec:
            log("  no run record; stop waiting")
            break
        rid, status = rec["run_id"], rec["status"]
        if status in ("pending", "running"):
            headers = {"Accept": "text/event-stream", "X-CSRF-Token": csrf()}
            if st.last_id:
                headers["Last-Event-ID"] = st.last_id
            jreq = urllib.request.Request(BASE_URL + f"/api/threads/{tid}/runs/{rid}/join", headers=headers)
            try:
                with opener.open(jreq, timeout=3600) as jr, open(OUT / f"e2e_turn{n}.sse", "a", encoding="utf-8") as raw:
                    try:
                        _read_sse(jr, raw, st)
                    except (OSError, http.client.HTTPException) as e:
                        # join 流再掉线: 回到状态轮询, 下一轮继续回接(bug-3032)
                        log(f"  join stream dropped ({type(e).__name__}); retry via status poll")
                        time.sleep(2)
            except urllib.error.HTTPError as e:
                log(f"  join {e.code}; retry via status poll")
                time.sleep(2)
            continue
        _fetch_terminal_truth(tid, rid, st)
        break
    if rejoins:
        log(f"  recovery rejoins={rejoins} saw_end={st.saw_end}")

    # dedup consecutive tool names
    seen, compact = set(), []
    for t in st.tools:
        if t not in seen:
            seen.add(t)
            compact.append(t)
    last_ai = ""
    for mid in reversed(st.ai_order):
        if st.ai_texts.get(mid):
            last_ai = st.ai_texts[mid]
            break
    forced_now = st.forced_count > prev_forced
    log(f"turn{n} tools({len(compact)}): " + " ".join(compact[:40]))
    if st.gap:
        log(f"turn{n} GAP encountered (recovered x{rejoins})")
    if st.interrupt_q:
        log(f"turn{n} INTERRUPT: {st.interrupt_q[:600]}")
    if st.error:
        log(f"turn{n} ERROR: {st.error}")
    log(f"turn{n} last_ai: {last_ai[:800]}")
    if forced_now:
        log(f"turn{n} FORCED_STOP: per-tool safety limit truncated the turn (frame count {st.forced_count})")
    # bug-2210 (2026-08-30): this gateway build no longer serializes ask_clarification
    # as a LangGraph __interrupt__ (run ends status=success; checkpoint state carries
    # no __interrupt__ key) — the model just stops and waits for the next user message
    # (soft pause). Surface the question text so the ANSWERS keyword flow keeps working.
    if st.interrupt_q is None and st.error is None:
        # 优先级(bug-3032, 复审 #1): 门证据 > 完成回执。交付回执常自然复述
        # "确认门2: 请确认终稿复核" + present_files——完成判定若在前会吞掉真门,
        # 阶段5 永远不跑 -> 假 PASS。ask_clarification 与门措辞一律先于完成分支。
        if "ask_clarification" in compact:
            log(f"turn{n} SOFT_CLARIFICATION: ask_clarification ended run without __interrupt__ (platform contract)")
            st.interrupt_q = last_ai or "clarification"
        elif any(_k in last_ai for _k in ("确认门", "待用户确认", "请确认", "待确认")):
            # variant: gate presented as plain text without ask_clarification
            # (skill-compliance miss); any gate phrasing in the final message
            # means the model is waiting for the user, not finished
            for _k in ("确认门", "待用户确认", "请确认", "待确认"):
                if _k in last_ai:
                    log(f"turn{n} SOFT_GATE: '{_k}' in final text without ask_clarification")
                    st.interrupt_q = last_ai or "gate"
                    break
        elif any(_m in last_ai for _m in ("全流程完成", "六件套", "已交付", "交付完成", "评分报告")) and "present_files" in compact:
            # completion recap — only with delivery tool evidence: files reach the
            # user solely via present_files, so markers inside a mid-pipeline stage
            # report ("阶段2-4完成报告" ending at 确认门2) must not end the run.
            log(f"turn{n} COMPLETION_RECAP: delivery markers + present_files -> treat as finished")
        elif forced_now:
            # 留 interrupt_q=None: main() 的 forced 分支接手, 发 TOOL_LIMIT_CONTINUE_MSG
            # (复审 #3: 强停不该走 ANSWERS 表——英文硬停文本匹配不到任何关键词,
            # 只会兜底成"确认, 请继续。"这种用户从未给出的罐头确认)
            log(f"turn{n} forced-stop -> defer to auto-continue branch")
        elif st.llm_error or TERMINAL_AI_ERR_RE.search(last_ai):
            # 复审 #16: 供应商级失败被归一化成助手文本(run success、无 error 帧),
            # 落进 PREMATURE_STOP 会 40 轮空转烧 quota——转成 error 让 main 停机
            log(f"turn{n} TERMINAL_LLM_ERROR: provider failure surfaced as assistant text -> stop nudging")
            st.error = f"terminal llm error: {last_ai[:200]}"
        else:
            # agnes premature turn end: clean success mid-stage (e.g. status note
            # then stop). 复审 #2: 只放哨兵, 绝不把 last_ai 喂给 pick_answer——
            # 状态通报含"分类/实体"字样会触发确认门罐头答案污染被测管线。
            log(f"turn{n} PREMATURE_STOP: clean end without gate/delivery markers -> neutral nudge")
            st.interrupt_q = PREMATURE
    return st.interrupt_q, last_ai, st.error, forced_now, st.forced_count, compact


def create_thread():
    req = urllib.request.Request(BASE_URL + "/api/langgraph/threads", data=b"{}", headers={"Content-Type": "application/json", "X-CSRF-Token": csrf()}, method="POST")
    with opener.open(req, timeout=60) as r:
        tid = json.loads(r.read().decode("utf-8"))["thread_id"]
    log(f"thread created: {tid}")
    return tid


def main(argv=None):
    global OUT, BASE_URL, MODEL, UPLOAD
    ap = argparse.ArgumentParser(description="bid-proposal-writing E2E 压测驱动(独立入口, 需活网关; 评分用 score_checkpoints.py)")
    ap.add_argument("--base", default=BASE, help=f"网关入口(默认 {BASE})")
    ap.add_argument("--upload", type=Path, default=DEFAULT_UPLOAD, help=f"上传输入件(默认 fixture {DEFAULT_UPLOAD.name}; agnes 基线重放用真实招标 PDF)")
    ap.add_argument("--model", default="agnes-2.5-Flash", help="模型名(config.context.model_name)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="日志目录(默认 backend/.deer-flow/e2e_bid/)")
    ap.add_argument("--resume", default=None, help="续作模式: 既有线程 id(跳过建线程+上传)")
    ap.add_argument("--resume-start", type=int, default=2, help="续作起始轮号(默认 2)")
    ap.add_argument("--resume-msg", default=None, help="续作首条指令(默认通用 continue)")
    ap.add_argument("--answers", type=Path, default=None, help="确认门应答表 JSON([[关键词, 回答],...]; 默认内置 ANSWERS)")
    ap.add_argument("--max-turns", type=int, default=40, help="轮数上限")
    args = ap.parse_args(argv)
    BASE_URL, MODEL, UPLOAD, OUT = args.base, args.model, args.upload, args.out
    if args.answers:
        ANSWERS[:] = [tuple(pair) for pair in json.loads(args.answers.read_text(encoding="utf-8"))]

    OUT.mkdir(parents=True, exist_ok=True)
    # 复审 #11: 评分器按 e2e_turn*.sse glob 收轮——上一跑的轮文件会混进本次打分
    # (旧违规轮 -> 假 FAIL / 旧交付 -> CP1 虚高)。全新跑开局清场; --resume 不清
    # (续作目录里的前段轮文件是证据, 续作请配新 --out 目录)。
    if not args.resume:
        for stale in OUT.glob("e2e_turn*.sse"):
            stale.unlink(missing_ok=True)
    (OUT / "e2e_progress.log").write_text("", encoding="utf-8")
    for _ in range(3):
        wait_healthy()
        try:
            login()
            break
        except Exception as e:
            log(f"login failed ({e}); retrying after gateway wait")
            time.sleep(5)
    if args.resume:
        tid = args.resume
        log(f"resume thread: {tid}")
        start_n = args.resume_start
        first_msg = args.resume_msg or CANCEL_RETRY_MSG
    else:
        tid = create_thread()
        upload(tid)
        start_n = 1
        first_msg = T1
    q, ai, err, forced, fcount, tools = turn(tid, start_n, first_msg, with_files=(start_n == 1 and not args.resume))
    forced_continues = 0
    premature_nudges = 0
    last_premature_ai = None
    # bug-3037 门轮空转停滞状态(仅 SOFT_GATE/SOFT_CLARIFICATION 应答路径推进;
    # premature/forced 轮打断链, escalated 每跑至多一次)
    stall_count = 0
    stall_escalated = False
    stall_seen = set()
    prev_tools = []
    for n in range(start_n + 1, args.max_turns + 1):
        if err and not q:
            if "Recursion limit" in err:
                log(f"turn{n} recursion burn -> auto-continue")
                q, ai, err, forced, fcount, tools = turn(tid, n, RECURSION_RETRY_MSG, prev_forced=fcount)
                continue
            if "CancelledError" in err or "cancelled" in err.lower():
                log(f"turn{n} cancelled -> auto-continue")
                q, ai, err, forced, fcount, tools = turn(tid, n, CANCEL_RETRY_MSG, prev_forced=fcount)
                continue
            log(f"stop: error without interrupt: {err}")
            break
        if not q and forced and forced_continues < 10:
            # loop-guard truncated a healthy long grind (e.g. validating N
            # candidate files one bash call each); continue, don't redo work
            forced_continues += 1
            stall_count, stall_seen = 0, set()
            log(f"turn{n} forced-stop -> auto-continue ({forced_continues}/10)")
            q, ai, err, forced, fcount, tools = turn(tid, n, TOOL_LIMIT_CONTINUE_MSG, prev_forced=fcount)
            continue
        if not q:
            log("no interrupt -> pipeline finished")
            break
        if q == PREMATURE:
            # 复审 #5: premature 无预算会把"措辞没踩中交付标记的真完成"烧满 40 轮;
            # 连续两轮末文完全一致 = 无进展, 视为完成收机
            if ai and ai == last_premature_ai:
                log(f"turn{n} no progress (identical final text) -> treat as finished")
                break
            last_premature_ai = ai
            if premature_nudges >= 5:
                log(f"turn{n} premature-stop nudge budget exhausted ({premature_nudges}/5) -> stop")
                break
            premature_nudges += 1
            stall_count, stall_seen = 0, set()
            ans = PREMATURE_CONTINUE_MSG
        else:
            # bug-3037: 门/澄清自动应答前的空转停滞判定
            stall_count, stall_escalated, stall_seen, action = stall_step(stall_count, stall_escalated, stall_seen, tools, prev_tools)
            if action == "abort":
                log(f"turn{n} STALL_ABORT: gate stall persists after escalation without delivery evidence -> stop")
                break
            if action == "escalate":
                ans = STALL_TERMINATE_MSG
                log(f"turn{n} STALL_ESCALATE: {STALL_N} gate turns, no new tool progress, no delivery evidence -> terminal instruction")
            else:
                ans = pick_answer(q)
        log(f"turn{n} answering with: {ans[:120]}")
        prev_tools = tools  # bug-3037: 先捕获旧值再覆盖, 下一门轮的窗口才是"本轮∪上轮"
        q, ai, err, forced, fcount, tools = turn(tid, n, ans, prev_forced=fcount)
    log(f"=== DONE thread={tid} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
