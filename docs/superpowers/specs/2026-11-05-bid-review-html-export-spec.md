# bid-review 报告 HTML 导出 Spec(2026-11-05)

> 挂账兑付:对齐审计收官记档「报告 html 导出(既有 422 白名单,属 M4+ 范围)」。
> 零配额纯后端小件;同 slice 完成 spec + 实施。

## 背景与目标

`GET /tasks/{id}/report?format=md` 已上线(Task 21):免责声明 → 元信息(复核耗时真聚合)→
可提交判定 → severity 四档 → 响应偏离表;非 md 格式 422「format 仅支持 md(html 导出属 M4)」。
本 spec 把 `html` 加入白名单,产出**单文件、可打印、无外部资源**的 HTML 报告,供浏览器
下载/归档/打印成 PDF。消费方:人工终审/存档;MCP 面零变化(agent 继续吃 md)。

## 裁决

1. **R1 原生渲染器,零新依赖**。新增 `_render_report_html`,与 md 共享端点内同一段数据
   准备(task/issues/feedback/deviations);不做 markdown→html 转换——引转换库是新依赖,
   且 escape-then-parse 有双重转义陷阱。报告结构固定,原生模板最短。
2. **R2 全量转义 + 强制下载**。所有动态文本(message/fix/evidence/deviation 字段/task 元数据)
   经 `html.escape()`;响应 `text/html; charset=utf-8` + `Content-Disposition: attachment;
   filename="bid-review-report-{id8}.html"`(与 gateway 既有 XSS 姿态一致:artifacts 对
   text/html 强制下载)。内联 `<style>`,无外部资源。
3. **R3 白名单语义不变式**。422 检查仍在取数前(whitelist 优先于 404/409);detail 更新为
   「format 仅支持 md|html」;md 通路字节级不变;`bid_review_report` MCP 工具保持硬编码
   format="md",代理面零变化。
4. **R4 内容对等,口径共享**。html 承载 md 全部语义节与措辞(免责声明/元信息+复核耗时/
   可提交判定/severity 四档+【待人工】/偏离表);false_positive 不进正文;致命红线判定式
   提取 `_fatal_hits(issues)` 供双渲染器共享,防两处口径漂移。

## 验收(测试即契约)

- `format=html` + done 任务 → 200,`text/html` + attachment `.html`;
- 正文含免责声明/可提交判定/命中红线措辞/【待人工】/偏离表节;false_positive 条目不出现;
- 动态 `<script>` 注入被转义(`&lt;script&gt;` 出现,原样 `<script>alert` 不出现);
- `format=pdf` → 422(新措辞);md 缺省/显式行为与既有测试全数保持;
- owner 404、半程 409 状态门在 html 下同口径。

## 实施清单

- [ ] 翻转 `test_report_rejects_html_format_and_other_owner`:html 422 断言 → done 后 200 html;
      新增未知格式(如 pdf)保 422 新措辞。
- [ ] 新增 `test_report_html_content_parity_and_escaping`(上述验收项)。
- [ ] routers.py:`import html`、`_fatal_hits` 提取、`_render_report_html`、白名单与双分支 Response。
- [ ] 全家门禁 + ruff + push `0\t0` + wolf/记忆记档。

## Out of scope

- 前端工作台导出按钮接 `?format=html`(前端层,现无调用方受影响;foreign WIP 期不动前端)。
- 打印专用分页 CSS / logo / 页眉页脚(M4+ 后续按需)。
