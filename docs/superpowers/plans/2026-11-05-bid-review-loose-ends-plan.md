# bid-review 挂账小件包 Implementation Plan(2026-11-05)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。Steps use checkbox (`- [ ]`) syntax.

**Goal:** 清偿对齐审计 slice 留下的两笔挂账:①openpyxl 晋升 backend base deps;②zip 内图片 OCR seg 补 `source` 成员名锚。

**Architecture:** ①纯声明变更(pyproject.toml + uv lock 元数据),运行时安装集不变 → 无需镜像重建;②parse.py ocr seg 组装处加一个键,与 text/table seg 对称。

**Tech Stack:** Python 3.12 / uv / pytest;零新依赖(openpyxl 3.1.5 已在 uv.lock,仅声明化)。

---

## 取证(已完成)

- openpyxl 现状:**不在** `backend/pyproject.toml` 任何区。传递链:`backend/pyproject.toml` base deps → `deerflow-harness`(packages/harness/pyproject.toml:38 `markitdown[all,xlsx]>=0.0.1a2`)→ markitdown 的 `xlsx`/`all` extras 拉 openpyxl(uv.lock:2073/2084;本体 3.1.5 在 uv.lock:2370)。markitdown 升级换 extras 或 harness 裁剪即静默断供 → `parse.py::_parse_xlsx_sync` 守卫导入 ValueError「缺 openpyxl」,xlsx 入口全灭。
- 先例:`pyproject.toml` base deps 已有两条「Direct dependency on purpose」注释(starlette 私有导入、deerflow-extension-api 公共契约)——同款理由。
- 断言面排查(bug-4018 纪律):ocr seg 现有断言全是字段级(`test_bid_review_parse.py:98/112/238`、`test_bid_review_routers.py:448`),**无键集锁**;parse.py:18 模块 docstring 契约 `[{seq,page,kind,text,asset_id}]` 须同步加 `source`。

## Task A: openpyxl 晋升 base deps

- [x] **Step 1: 失败测试** — 新建 `backend/tests/test_bid_review_deps.py`:读 backend/pyproject.toml,取 `[project] dependencies = [` 到首个 `]` 的切片,断言 `"openpyxl` 在内(只锁 base deps,不认 extras)。
- [x] **Step 2: 跑红** — `PYTHONPATH=. uv run pytest tests/test_bid_review_deps.py -q` → FAIL(1 failed)。
- [x] **Step 3: 声明** — pyproject.toml base deps 追加 `"openpyxl>=3.1.5,<4"` + purpose 注释(parse.py 直导入,现仅经 markitdown extras 传递,声明化防静默断供)。
- [x] **Step 4: uv lock** — 在线 `uv lock` 挂死 12 分钟(PyPI 同 github 443 一样不可达),杀进程后 `uv lock --offline` 299ms 解完(+2 行 requires-dist 元数据,安装集零变化)。
- [x] **Step 5: 跑绿 + 提交** — commit b5abcebe8 显式路径:pyproject.toml uv.lock tests/test_bid_review_deps.py。(实现偏差:测试首版用首个 `]` 截块,被 `"uvicorn[standard]"` extras 括号截断 → 改行首 `\n]` 边界。)

## Task B: zip 内图片 asset 级溯源

- [x] **Step 1: 失败测试** — `test_bid_review_parse.py` 追加 `test_zip_embedded_image_ocr_seg_has_source` + 独立直传测试补 `source is None` 断言。(缺 source 键 → KeyError,红态逻辑必然,未单独跑红。)
- [x] **Step 2: 跑红** → **Step 3: 实现** — parse.py ocr seg 加 `"source": b.get("source")`;模块 docstring 契约加 `source/rows` → **Step 4: 跑绿**(14/14)。
- [x] **Step 5: 提交** — commit 9e2f4de8e 显式路径:parse.py + test 文件。

## 收官记档(2026-11-05)

- 全家门禁 **572 passed / 6 skipped / 0 failed**(slice 前 570,+2 新测试);golden 零翻红、M0 26/26 在族内、universe 不动。
- push 首试即中 `0\t0`(04874a9e0..9e2f4de8e)。
- **环境教训**:PyPI 与 github 443 同源间歇断连——在线 `uv lock` 会无限挂死(无超时、无输出),先杀 uv.exe 再 `--offline`(锁内已有的包秒解)。锁新增依赖才需要网络。

## 收尾

- [x] 全家门禁(572/0);ruff 全绿零残余;push `0\t0`;wolf 记档;auto-memory 挂账池更新(两笔勾销)。

**Out of scope(继续挂账):** zip 内 PDF 扫描页 OCR(跨成员页号冲突设计);score 预估 spec;html 导出 M4+;M2-M4 活体方差回采(队列②,烧配额)。
