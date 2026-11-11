# 批十八:OCR 引擎切换 paddleocr-vl(零代码配置批,bid-review P1 β18)计划

日期:2026-11-11 · 分支:main-dev-fork · 前置:批十七(6b689f5e8,已推)
触发:用户供地址「paddleocr-vl-1.6的访问地址192.168.5.253:8111」(批十四开工提醒兑现)

## 背景

挂账「OCR 管道边界」(批十四;realcase 扫描件 OCR 边界=保证金真违规静默)。
服务实测:**llama.cpp server**(GGUF 量化,`/v1/models`=`PaddleOCR-VL-1.6-GGUF.gguf`,
`/health` ok)→ OpenAI 兼容 vision 协议,正落 `parse._ocr_openai_vision` 既有通路。
活体 smoke(gateway 容器 venv python,fitz 造图 3 行中文+数字):**5.0s,逐字全对**,
`choices[0].message.content`+usage 标准形状。

## 机制(2026-11-11 调查,parse.py/ocr_resolve.py/settings/routers.py 对读)

- `worker.py:688 build_ocr_fn(db)` 每任务现读设置:SystemConfigService 无缓存 →
  `default_ocr_engine`=注册表名 → `_ocr_openai_vision(entry)`;=builtin/失效 → 内建
  eai-flow-ocr :8010。**热切换,零重启**。
- 注册表:`PUT /api/extensions/settings/ocr/services`(super_admin,api_key 掩码
  write-only,掩码回显保 stored truth);`base_url` 拼 `/chat/completions` → 须含 `/v1`。
- `POST /settings/ocr/validate`:1x1 图活体 ping(mirror models/validate)。
- 消费面:bid_review(docx 内嵌图/PDF 扫描页/独立图)+ contract_price + translation
  + geo_samples 全部跟随全局默认引擎。

## 裁决表

| 杠杆 | 裁决 | 理由 |
|---|---|---|
| 集成方式 | **纯配置**:注册表条目+默认引擎切换,零代码 | 双引擎架构既在(cpa v3 M3);新引擎分支=YAGNI |
| api_key | 占位非空串 `local` | llama.cpp 忽略 Bearer;resolve 仅拒掩码/空 |
| base_url | `http://192.168.5.253:8111/v1` | 拼 /chat/completions 后即 smoke 已验路径 |
| 切换范围 | **全局默认**(default_ocr_engine=paddleocr-vl-1.6) | 设置即全局杠杆,逐消费方 scoping=新代码 YAGNI;回滚=PUT 改回 builtin 秒级 |
| 验证 | validate 活体 + 真实件复采×3 + judge 定点 | 扫描件附件段/deposit 链复活与否=本批唯一行为问句 |

## 任务

- [x] T1 配置面:PUT ocr/services 注册条目(实际:**原地更新既有 `paddleocr-vl` 条目**——
  旧址 192.168.2.38:8111 系机器迁移前 stale 值,保名防其他消费方引用断链;base_url=
  http://192.168.5.253:8111/v1,model=PaddleOCR-VL-1.6-GGUF.gguf,api_key 空=llama.cpp
  免鉴权,resolve 仅拒掩码/空 base_url)→ POST ocr/validate **ok 810ms** → PUT /config
  default_ocr_engine=paddleocr-vl → GET 双回读干净。API 通道:EAI 门面 login
  (body 键=`username` 非 email)+ CSRF 双提交 cookie。
  修正:realcase 探针喂 convert_file_to_markdown 预转换文本,不经过 parse_raw/build_ocr_fn
  ——**探针对 OCR 引擎是盲区**,T2 须 parse_raw 直驱仪器。
- [x] T2 A/B 复采:parse_raw 直驱(realcase-bid.docx 46 内嵌图/39 OCR jobs,tender 0 张;
  sqlite 夹具 _TABLES+system_config 播种两态)。**T1.5 管道双缺陷**(A/B 活体揪出,升格为
  本批代码交付):bug-4289 空 Bearer 死锁(修前 B 侧 0/39 全空)+bug-4290 fitz 包 PDF 逃网
  (修前 A 侧 EMF FzErrorFormat 炸整文档)→双修双钉,门 772→**774p/6s/0f**,lint 双清。
  A/B 修后:A=401.4s 38/39 16831 字;B=2198s 31/39 16083 字(8 空=7 ReadTimeout+1 EMF 400;
  B 段含与 e2e 首跑争抢污染——单服务仪器须串行律)。**覆盖面持平**:关键词命中同 4 资产
  同关键词(票据×2/银行/凭证),逐资产质量对读相当;「paddleocr-vl 复活保证金链」假设
  **证伪**——46 图保证金 0 命中(图像=审计报告/票据,保证金语义在文本层 bid 3/tender 23)。
  下游 leg(e2e 独跑,paddleocr-vl seeded):bid 47k 字→抽取 truncation retry 吃住(批十三
  机制)→review 391.9s→**9 issue 全 UNKNOWN 字段缺失 need_human,gate=PENDING_HUMAN,
  零 FAIL 零 ERROR**,与批十七 md 路径 9U·0F 样本同形,规则 id 级零翻转。
  裁决:引擎切换本样本无增益+5.5×成本;default=paddleocr-vl 维持(用户供址意图),
  数据在案,回切 builtin 一 PUT 即可(设置页/API,秒级热切)。
- [x] T3 收口:plan 勾兑 + spec 批十八段 + wolf 三件(buglog 4289/4290+cerebrum 六条+
  memory)+ session memory + closure。提交面:代码 1(parse.py+钉)+docs 2(plan -f+spec)。

## 挂账

- 模型召回边界(降格:需实填充业绩/清单样本再裁,批十七遗留,本批不动)。
