# 法规标准 tab:RAGFlow 知识库种子配置对齐 + 导入链路行业标记 — 设计

- 日期:2026-09-03
- 状态:设计已确认(待用户审阅本 spec 后转实施计划)
- 关联:`docs/superpowers/specs/2026-09-02-ragflow-upgrade-v0.27.1.md`(RAGFlow v0.27.1 升级)、bug-3077

## 0. 背景与实测依据

RAGFlow v0.27.1 升级后对法规标准类文书做了三轮分块 A/B(同文档、同 embedding=bge-m3、同实例):

| 语料 | 对比 | 结论 |
|---|---|---|
| DZ/T 0033-2020(标准,44p,字母前缀附录) | laws / manual / book / naive 默认 / naive 调参 | **naive-384 调参最优**(附录条款对齐 24.3% vs laws 0%);laws/manual/book 出局 |
| 水土保持法.docx(法律,6章60条,无标题样式) | laws / naive-384 | **laws 最优**:每条一块+章标题路径,条界完整;naive-384 条界模糊(块从上一条半句开始) |
| 现状缺陷 | init-ragflow 种子 | `RAGFLOW_DATASET_GROUPS` 仍为 standards→**manual**(A/B 出局且对 .txt 抛错);完全不传 parser_config;已存在库直接跳过,永不收敛到调优配置 |

已确认的设计决策(用户逐项裁定):

1. 行业前缀来源:**专用「行业领域」下拉字段**(受控,选项来自「行业标签集」),不用关键词识别、不用部门映射。
2. 法规库(ragflow-laws-legal)分块器:**保持 laws**(A/B-4 实测对第X条文体最优)。
3. init-ragflow 幂等策略:**幂等收敛**——已存在的库比对种子配置,不一致则 PUT 更新。
4. 种子配置存放:**代码常量**(law/service.py,与 `_LAW_CHUNK_METHOD` 同处)。

## 1. 设计 A:init-ragflow 幂等种子(后端)

### 1.1 种子常量

`law/service.py` 新增 `_KB_SEED_CONFIG`,删除 `RAGFLOW_DATASET_GROUPS`(双份真相,standards→manual 已过时),所有引用点(routers.init-ragflow、service 内循环、`_ensure_kb_registered` 的 chunk_method 实参)改从种子派生;同步修正模块头"manual 按章节标题分块"的过时注释。

```python
_KB_SEED_CONFIG = {
    "ragflow-laws-legal": {          # 法律/法规/规章(第X条文体),A/B-4 实测 laws 最优
        "chunk_method": "laws",
        "parser_config": {"layout_recognize": "DeepDOC", "auto_keywords": 0, "auto_questions": 0},
        # laws 无 chunk_token_num 旋钮(实测死旋钮),不配置
    },
    "ragflow-laws-standards": {      # 标准/规范,A/B-1 实测 naive-384 最优
        "chunk_method": "naive",
        "parser_config": {
            "chunk_token_num": 384,
            "delimiter": "\n。！？；",   # 首字符为真实换行符(API 不做 unicode_escape)
            "layout_recognize": "DeepDOC",
            "html4excel": True,
            "auto_keywords": 0,
            "auto_questions": 0,
            "enable_children": False,
            "tag_kb_ids": "RESOLVE_AT_RUNTIME",   # 见 1.2
            "topn_tags": 3,
        },
    },
}
```

### 1.2 幂等收敛流程(routers.init-ragflow 重写)

每库依次:
1. `get_dataset_by_name` 不存在 → `create_dataset(name, description, chunk_method=种子.chunk_method, parser_config=种子.parser_config)`(tag_kb_ids 见 1.3)→ 计入 `created`。
2. 已存在 → `get_dataset` 读回 `chunk_method`+`parser_config`,与种子做**受限键比对**(只比种子中出现的键;RAGFlow 回读会填充大量默认键,忽略之):
   - 一致 → 计入 `aligned`;
   - 不一致 → `update_dataset(id, chunk_method=..., parser_config=种子.parser_config)` → 计入 `updated`(附 diff 摘要);
   - PUT/GET 失败 → 计入 `failed`(现状字段)。
3. `_ensure_kb_registered` 的 chunk_method 实参改从种子取。

响应模型 `RAGFlowInitResponse`:`created/failed/registered` 保留,`already_exists` 改为 `aligned`(列表)+ `updated`(列表)+ `diffs`(可选明细)。前端 `LawLibrary.tsx` 对应文案更新。

### 1.3 行业标签集绑定

init 时按名称解析「行业标签集」dataset:存在 → 其 id 填入 standards 种子的 `tag_kb_ids`;不存在 → 留空 `[]` 并 WARNING 日志(不阻断 init)。已知限制(写入 spec,非阻塞):v0.27.1 实测块级自动贴标(tag_kwd)未生效(0/33,检索层确认),行业标记当前运营层为文档名前缀(见设计 B);上游修复后此绑定即生效。

### 1.4 行业领域下拉数据源(2026-09-04 修订:业务字典为单一真相源)

前端 `useLawIndustries` 直读**业务字典 tab → 业务领域字典**(`kfApi.listDictItems("industry")`,即 `GET /api/kf/dictionaries/industry`,按 sort_order 排序、过滤 enabled)。**不硬编码**行业名单,不设兜底(字典为空=下拉仅"不标记行业",由业务字典 tab 维护条目)。初版的 `GET /api/kf/laws/industries` 端点、`IndustriesResponse`、`merge_industries`/`_DEFAULT_INDUSTRIES` 硬编码兜底已整体拆除。

## 2. 设计 B:导入链路行业标记(前后端)

### 2.1 前端 `ImportLawModal.tsx`

新增「行业领域」下拉(可空,placeholder "不标记行业"):选项来自 1.4 端点。提交时 multipart 追加 `industry` 字段。

### 2.2 文档名组装(后端单点)

`law/service.py` 新增纯函数:

```python
def build_ragflow_doc_name(industry: str | None, law_number: str | None, title: str, ext: str) -> str:
    parts = f"【{industry}】" if industry else ""
    num = f"{law_number} " if law_number else ""
    return f"{parts}{num}{title}.{ext}"
```

sync 上传路径的 `upload_name` 改由该函数生成(文件上传与纯文本两条分支统一);重同步时按 laws.industry 重建,手工前缀做法自动化。RAGFlow 文档改名 PATCH 保持扩展名一致(上游校验)。

### 2.3 持久化

- 复用既有 `LawCreate.sector` 字段("Applicable industry",存 metadata_json.sector,service.py:401/451 读写链路已通)承载行业领域——**零 DDL**;不新增 laws.industry 列(避免与 law_type="industry"(行业标准)语义撞名)。导入/编辑时保存。
- 写入 RAGFlow `meta_fields.industry`(随现有 update_document_metadata 链路)。
- 其余表单字段(发布部门/生效日期/关键词/被引用法规)维持 `meta_fields` 现状,不做注入增强(见 Non-goals)。

## 3. Non-goals

- 不做"表单字段注入块内容"类增强(发布部门/日期/关键词/被引用对 RAGFlow 向量检索无收益,价值在 EAI 侧筛选,现有 meta_fields 已承载)。
- 不做块级行业贴标的自研替代(等待上游 tag_kb_ids 生效;已留绑定)。
- 不改 legal 库的 laws 分块器(A/B-4 实测其对第X条文体最优)。
- 不处理 `_LAW_CHUNK_METHOD` 中 law/regulation/rule→laws 的既有映射(语义正确)。

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| 行业标签集不存在 | industries 返回空;前端提示可留空;init 种子 tag_kb_ids=[] |
| init 时 RAGFlow 不可用 | 503(现状) |
| 已存在库配置 PUT 失败 | 计入 failed,不中断其余库 |
| 导入时行业为空 | 文档名无前缀段, laws.industry=NULL |
| RAGFlow 不可用时导入 | 现状:本地入库成功、sync 静默跳过(不变) |

## 5. 测试

- 单元(backend/tests/test_law_kb_seed.py):
  - `build_ragflow_doc_name`:有/无行业、有/无标准号、扩展名拼接、超长标题不截断(RAGFlow 无文件名长度限制,常规标准名远小于限制,截断反而丢信息);
  - 种子 diff 函数:一致→aligned、chunk_method 不一致→updated、仅种子键参与比对;
  - industries 解析:标签集存在/不存在。
- 手工验证清单:
  1. 对现有两库(已手工调优)执行 init-ragflow → 响应 `aligned`(legal 可能 `updated`:补 DeepDOC/auto0);
  2. 删除 RAGFlow 中 laws-standards(测试环境)→ init → `created` 且 readback chunk_token_num=384、tag_kb_ids=行业标签集 id;
  3. 导入一条带行业领域的技术标准(可用 HJ 130-2019.pdf 手工上传)→ RAGFlow 文档名=`【环境评价】HJ 130-2019 …`;
  4. `GET /api/kf/laws/industries` 返回三个行业。

## 6. 影响面

- 后端:`law/service.py`(种子常量、build_ragflow_doc_name、sync 上传命名)、`law/routers.py`(init 重写、industries 端点)、`law/schemas.py`(响应模型、LawCreate/Response 加 industry)、extensions `database.py`(laws 加列)。
- 前端:`ImportLawModal.tsx`(行业下拉)、`LawLibrary.tsx`(init 响应文案)、`api/index.ts`(industries API)。
- 不改 RAGFlow 上游、不改 harness。
