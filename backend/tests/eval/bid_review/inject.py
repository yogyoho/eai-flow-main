#!/usr/bin/env python3
"""注入算子:对干净 field_snapshot 做最小扰动,产金标准正样本。
MUT-001~017 全目录与规则映射见设计文档 §7(转录自素材③)。
用法: python inject.py --case cases/DEMO-001 --mut MUT-001 --out out.json
"""

import argparse
import json
from pathlib import Path


def mut_001(f):  # 总价超限价 1 元 → L1-009
    f["bid.total_price"] = float(f["tender.max_price"]) + 1.0
    return f


def mut_002(f):  # 明细加总与总价错位 1 分 → L1-010
    f["bid.subtotal"] = round(float(f["bid.total_price"]) - 0.01, 2)
    return f


def mut_003(f):  # 大写金额与数字不一致 → L1-010
    f["bid.total_price_words"] = "壹元整"
    return f


MUTS = {"MUT-001": mut_001, "MUT-002": mut_002, "MUT-003": mut_003}
# ponytail: MUT-004~017 从素材③ MUT 目录逐条转录,录一个注册一个,缺席即报错不静默
#
# TODO(转录源不可达,2026-10-29 Task 19): 素材③ MUT 目录的逐条字段变换未随计划归档进仓,
# 仅以下映射关系可达(设计文档 §7 / 实施计划 Task 19),待素材转录后逐条注册(每个 2-4 行字段变换):
#   MUT-007 → 残留旧项目名,可附带触发 L3-001/L3-002/L3-016
#   MUT-011 → L3-007
#   MUT-012 → L3-008
#   MUT-013 → L3-013
#   MUT-014 → L1-012
#   MUT-015 → L3-003
#   MUT-016 → L1-007
#   MUT-017 → L3-014
#   MUT-018 → 属 L4,v1 不做
#   (MUT-004/005/006/008/009/010 映射关系同样待素材转录补齐)


def load_clean_snapshot(case_dir: Path) -> dict:
    """干净底盘 field_snapshot:优先 fields_clean.json(计划口径,未来 e2e 案独立落盘);
    缺席时回退读 case.yaml 声明的 field_snapshot(Task 20 直灌同源,DEMO 骨架口径)。"""
    clean = case_dir / "fields_clean.json"
    if clean.exists():
        return json.loads(clean.read_text(encoding="utf-8"))
    import yaml

    case = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
    snap = case.get("field_snapshot")
    if not snap:
        raise SystemExit(f"{case_dir} 既无 fields_clean.json 也无 case.yaml field_snapshot")
    return snap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--mut", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    snap = load_clean_snapshot(Path(a.case))
    if a.mut not in MUTS:
        raise SystemExit(f"{a.mut} 未转录:按设计文档 §7 MUT 目录补 MUTS 条目")
    out = MUTS[a.mut](dict(snap))
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"injected {a.mut} -> {a.out}")


if __name__ == "__main__":
    main()
