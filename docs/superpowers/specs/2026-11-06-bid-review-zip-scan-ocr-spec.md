# bid-review zip 内 PDF 扫描页 OCR Spec(2026-11-06)

> 挂账兑付:对齐审计⑥「zip 内 PDF 扫描页转诚实占位段(跨成员页号冲突,OCR 挂账)」。
> 零配额纯后端;最后一个零配额挂账。

## 背景

zip 内 PDF 成员的扫描页(空文本层)目前产占位文本段
「[第 N 页为扫描页:zip 内 PDF 暂不支持扫描页 OCR,请单独上传该 PDF]」——扫描页
内容完全不可见。当时挂账的原因是页号归属:zip 是单 doc(一个 segments.json),
多成员页号撞车,而定位契约按单文档页码。对齐审计⑥落地后 seg 已有 `source` 成员名锚,
(source, page) 二元组在 seg 级无歧义——挂账的前置条件已满足。

## 裁决

1. **R1 扫描页走既有 OCR 通路,真页码**。zip 内 PDF 扫描页块携带 blob
   (`{kind:"scan", page:n, blob:png}` + 解包时附 source)进 parse_raw 既有 scan 分支:
   OCR + asset 落盘 + `kind:"ocr"` seg,**页号=成员内真页码**——不做全局偏移
   (偏移页码=编造,与「投标总价」同罪)。占位段废除。
2. **R2 锚=(source, page) 无歧义**。seg 层 source+真页码即唯一锚;OCR job 名带
   source 前缀(如 `docs/scan.pdf#page-2.png`)便于日志追溯。
3. **R3 溯源端点 ?source= 消歧**。`GET /docs/{doc_id}/content` 增可选 `source` 参数:
   先按成员过滤候选池,再走既有 page/quote 命中;**整页窗口计算同样限制在池内**
   (顺手修掉既有跨成员混页窗口歧义:`?page=N` 的窗口此前会把两个成员的同一页号段
   混在一起)。缺省不传 → 行为字节不变;非 zip 文档传 source → 池空 404「未定位到
   原文」(锚不存在即未定位,诚实)。**evidence.source 端到端(engine prompt/verify/
   前端)不在本 slice**——多成员 zip 的 evidence 页码歧义是既有条件,本 slice 不引入
   不恶化,端到端锚升级另立项。
4. **R4 失败隔离继承**。zip 扫描页 OCR 失败 → 空文本 ocr seg(既有隔离,不炸任务),
   asset 保留(人工可看图)。
5. **R5 断言面零翻红**。占位文案无测试锁(已清扫);既有 zip 测试
   (`test_zip_members_parsed_with_source` 等)、`test_doc_content_and_asset_endpoints`
   (非 zip 路径 page= 直取)、不传 source 的既有行为全部保持。

## 验收(测试即契约)

- zip(单 PDF 成员:页 1 文本层 + 页 2 扫描页)→ text seg(page=1, source=成员)+
  ocr seg(page=2, source=成员, asset_id, OCR 文本);占位文案不再出现;
- zip(两个 PDF 成员,各自页 2 扫描页)→ 两条 ocr seg 同 page=2、source 各归其主;
- OCR 失败 → 空文本 ocr seg + asset 在;
- 端点:多成员 zip `?page=1` 不传 source → 既有行为(首个命中);`?source=B&page=1`
  → B 成员的页;窗口不跨成员;
- 非 zip PDF 全通路零翻红(scans dict 既有路径不动)。

## 实施面

- parse.py:`_blocks_for_bytes` PDF 分支回 scan 块带 blob;parse_raw scan 分支
  `png = b["blob"] if "blob" in b else scans[b["page"]]` + job 名 source 前缀;
  模块/函数 docstring 同步。
- routers.py:`get_doc_content` 增 `source: str = ""` 参数 + 池过滤 + 池内窗口。
- 测试:parse 2-3 个 + routers 1 个(上述验收)。

## Out of scope

- evidence.source 端到端(LLM 契约/verify/前端 chip)——另立项;
- 扫描页 OCR 质量/配额调优(OCR_CONCURRENCY 既有);
- zip 内 PDF 文本页与独立上传 PDF 的去重合并。
