#!/usr/bin/env python3
"""矿井档案层（spec D3 文件契约）。

档案文件 = stages/tunneling.json forms.profile 族的 values 字典（22 扁平字段（含 J11 refuge 七字段），
不发明第二套 schema——validate 复用 ingest.validate_values 单一真源）。
跨运行协议：首跑建档（mine_forms 逐族 ask_clarification）→ load 落 data/00_profile.json
→ 档案 md 随交付 present_files 进 docmgr；后续线程用户带档案文件进线程 → load → 门1 自动覆盖。
三命令: validate / summary / load。rc: 0 成功 / 1 校验失败或用法错。"""
import argparse
import importlib.util as _u
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
_spec = _u.spec_from_file_location("tun_ingest", SCRIPTS / "ingest.py")
ingest = _u.module_from_spec(_spec)
_spec.loader.exec_module(ingest)

EXIT_OK, EXIT_ERROR = 0, 1
DEFAULT_STAGE = SCRIPTS.parent / "references" / "stages" / "tunneling.json"
# 展示分组（仅 summary/文档渲染用——字段名与 forms.profile 一一对应）
GROUPS = [
    ("矿井标识", ["mine_name", "group_name", "reg_no_format", "team_name", "shift_system"]),
    ("灾害参数", ["gas_grade", "hydro_type", "spontaneous_tendency", "coal_dust_explosion"]),
    ("系统配置", ["development_mode", "ventilation_mode", "supply_voltage", "monitoring_system"]),
    ("会审名单", ["audit_units"]),
    ("避灾与自救", ["self_rescue_model", "self_rescue_count", "self_rescue_distance_m", "escape_route_fire", "escape_route_water", "escape_route_roof", "avoidance_systems"]),
    ("版本", ["archive_date"]),
]


def _stage_fields(stage_path: str) -> dict:
    """返回 forms.profile 完整族 spec（ingest.validate_values 吃 {'fields':[...]} 字典而非裸 list——对抗评审 P0）。"""
    stage = json.loads(Path(stage_path).read_text(encoding="utf-8"))
    try:
        return stage["forms"]["profile"]
    except KeyError:
        raise ValueError(f"阶段 schema {stage_path} 缺 forms.profile 族（档案层只服务 profile 族）") from None  # M3


def _read_archive(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):  # I2 形状守卫：数组/标量档案直接可读报错，防 len()/get() 深处 TypeError
        raise ValueError("档案必须是 JSON 对象(dict)，收到 " + type(data).__name__)
    return data


def cmd_validate(args) -> int:
    values = _read_archive(args.input)
    spec = _stage_fields(args.stage)
    errors = ingest.validate_values(spec, values)  # 返回错误清单而非抛 ValueError
    if errors:
        print(f"PROFILE_INVALID: {'; '.join(errors)}")
        return EXIT_ERROR
    print("PROFILE_OK:", len(values), "fields")
    return EXIT_OK


def cmd_summary(args) -> int:
    values = _read_archive(args.input)
    print(f"=== 矿井档案摘要（{values.get('mine_name', '?')}）===")
    for title, keys in GROUPS:
        row = "；".join(f"{k}={values.get(k)!r}" for k in keys if k in values)
        if row:
            print(f"[{title}] {row}")
    print(f"提示: 档案日期 {values.get('archive_date', '未填')}——矿井条件有变先更新档案再编新规程（C12 漂移检测会比对正文）")
    print("PROFILE_SUMMARY")
    return EXIT_OK


def cmd_load(args) -> int:
    values = _read_archive(args.input)
    spec = _stage_fields(args.stage)
    errors = ingest.validate_values(spec, values)  # 返回错误清单而非抛 ValueError
    if errors:
        print(f"PROFILE_INVALID: {'; '.join(errors)}")
        return EXIT_ERROR
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)  # 对抗评审 P0：write_form_values 不建目录
    ingest.write_form_values(args.stage, args.data_dir, "profile", values)
    print("PROFILE_LOADED: data/00_profile.json（门1 完备性已覆盖档案族）")
    return EXIT_OK


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="profile.py", description="矿井档案 validate/summary/load")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "summary"):
        s = sub.add_parser(name)
        s.add_argument("--input", required=True)
        s.add_argument("--stage", default=str(DEFAULT_STAGE))
    s = sub.add_parser("load")
    s.add_argument("--input", required=True)
    s.add_argument("--stage", default=str(DEFAULT_STAGE))
    s.add_argument("--data-dir", required=True)
    args = p.parse_args(argv)
    try:
        return {"validate": cmd_validate, "summary": cmd_summary, "load": cmd_load}[args.cmd](args)
    except (OSError, ValueError, KeyError) as exc:  # I2/M3：ValueError 含 JSONDecodeError（其子类）
        print(f"PROFILE_ERROR: {exc}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
