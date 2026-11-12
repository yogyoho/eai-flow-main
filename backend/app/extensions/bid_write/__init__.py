"""bid_write —— 投标商务智能写作扩展(EAI-CUSTOM 2026-11-13,批十九 P0-M0)。

写作端=审查端(bid_review)的「生成端」:共用 tender.* 字段契约(import 复用
extract.FIELD_TYPE_CONTRACTS,不复制不造平行 yaml)、共用规则包(M2 预审查
复用 rule_runner/eval_core)、素材实体(P1)。本模块 M0 范围:F1 商务要素
解析与响应矩阵(tender-only 抽取→response_matrix 落库)+人工确认卡点。

边界(设计稿 §二/§十):不生成技术参数选型计算;不虚构业绩/证书/检测数据;
不代签章不代提交;生成稿须人工终审。技术卷编排见 skills/public/bid-proposal-overall
及配对 bid-technical(编排面已在,本模块是其确定性服务后座)。
"""
