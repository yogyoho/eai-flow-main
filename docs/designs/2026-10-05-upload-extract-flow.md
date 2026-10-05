# OntoStudio 文件上传直连抽取——一体化流(G3 后续, D16 方案 A)

日期:2026-10-05 · 状态:DESIGNED(待实施) · 前置:G3 直连抽取已落地(757922f04)

## 用户故事

本体建模用户上传一份 docx/txt → 系统自动:存卷 → 建 kf_samples 行(入 EAI 样例库,双向可见)→ 规则抽取补 outline_json → 建抽取任务(含进度)→ 消解审核 → 装载。**全程一次操作**。

## 数据流

```
POST /ingest-tasks/upload (multipart: file + force_review)
  ├→ 存 /data/kernel/kf-uploads/{sample_uuid}.{ext}
  ├→ INSERT kf_samples (id=sample_uuid, title=原文件名, source_path=卷路径,
  │                     file_hash=sha256[:32], scenario='other', status='parsed')
  ├→ INSERT ingest_tasks (sample_id=sample_uuid, status='queued')
  └→ background: _run_task(sample_uuid, ...)
       ├→ outline NULL + 源文件在 → run_extract(源文件)
       │    ├→ outline_json 写回 kf_samples(样例库积累)
       │    └→ converter 白名单清洗 → dg_*(force_review → 全量待审)
       └→ done(进度列 ✓)
```

## 后端

| 件 | 说明 |
|----|------|
| `POST /ingest-tasks/upload` | multipart(file + force_review);扩展名白名单 .txt/.docx;大小 ≤150MB(沿用 extract.py 守卫);file_hash 幂等(同 hash 重复上传 → 409 或返回已有) |
| kf_samples 双写 | OntoStudio 上传入口 + EAI 向导入口,同库同 schema,样例双向可见 |
| 抽取 | `run_extract(source_path)`(G3 已移植的 text_extract 包);仅 EIA 规则域 |
| 进度 | 复用 G6(stats.progress) |

## 前端

| 件 | 说明 |
|----|------|
| 表单双入口 | 「上传新文件」file input + 「选择已有样例」下拉,并列 |
| 上传反馈 | 上传中进度/完成后任务行出现在队列 |
| 域限制标注 | 表单如实标注:当前规则抽取仅支持环评域 |

## 边界与依赖

- 规则抽取仅 EIA 域——其他域文件待 LLM 通道(表单标注)
- kf_samples 双写需确认无 EAI 侧触发器/约束冲突(同库同 schema,预期安全)
- 大文件上传超时:FastAPI UploadFile 流式写入,无框架限制
