"""交付契约解析(v4 通用化)——present_files / sandbox_sync / artifacts GET 三端共用。

EAI-CUSTOM (bug-2225 契约门; bug-3109 v4 通用化)。背景: 管线技能以 build_output.py
产交付物并在 outputs/ 写放行凭据; agent 绕过管线手拼 .md 曾交付成功(bug-2225)。
v4 分册架构后 bid-proposal-writing 的交付物从单文件变为册集, 原单名契约
(manifest.deliverable) 无法承载——本模块把三端各自的重复解析收口为一处:

契约版本 1 (v4 WP-2.3, 设计稿 docs/designs/bid-proposal-writing-v4-volume-architecture.md):
    manifest = {
        "skill": str(可选, 技能源声明, 错误指引用),
        "version": int(可选, 契约版本; 高于本模块支持版 → 显式报错不静默, 3A),
        "deliverables": [文件名...](新契约, 册集/多文件),
        "deliverable": str(geo 旧契约, 单文件——向后兼容, 旧 manifest 不受影响),
        "aux_md": [辅助 .md...](可选, 技能申报的确认门工件白名单——条款清单/补遗
                  diff 表等非 build 产物仍合法呈现; 由管线 build 写入, agent 不可报批),
    }
解析规则(向后+向前兼容, eng-review C1/C2/3A):
    - outputs/ 无 .delivery-contract 标记 → 契约关闭(非管线线程全放行)
    - deliverables[] 在场 → 新契约(列表放行, aux_md 并入)
    - 否则 deliverable 非空字符串在场 → 旧契约(单名放行)
    - 两者都不在场/manifest 损坏 → unknown(显式报错, 拒 .md——绝不静默放行)
    - version 高于 MANIFEST_CONTRACT_VERSION → too_new(显式报错)

升级注意: 上游升级保留本模块; 三端消费方(present_file_tool/sandbox_sync/
artifacts router)只准经本模块解析 manifest, 不得自行 json.loads 字段——
契约演进只改这里一处。
"""
from __future__ import annotations

import json
from pathlib import Path

DELIVERY_CONTRACT_NAME = ".delivery-contract"
DELIVERY_MANIFEST_NAME = "delivery_manifest.json"
MANIFEST_CONTRACT_VERSION = 1

# resolve_manifest 的 status 取值
STATUS_OFF = "off"  # 无契约标记: 非管线线程
STATUS_MISSING = "missing"  # 有标记无 manifest: 管线从未成功 build
STATUS_UNKNOWN = "unknown"  # manifest 损坏/无法解析/未知契约字段
STATUS_TOO_NEW = "too_new"  # version 高于本平台支持
STATUS_OK = "ok"


def resolve_manifest(outputs_dir: Path) -> tuple[str, dict]:
    """读并解析 outputs/ 下的交付凭据(同步体; 调用方负责线程卸载, 勿在事件循环直呼)。

    返回 (status, data)。status ∈ off/missing/unknown/too_new/ok; data 携带
    skill(str|None)/allowed(set[str], 仅 ok)/version。
    """
    if not (outputs_dir / DELIVERY_CONTRACT_NAME).exists():
        return STATUS_OFF, {}
    manifest_path = outputs_dir / DELIVERY_MANIFEST_NAME
    if not manifest_path.is_file():
        return STATUS_MISSING, {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return STATUS_UNKNOWN, {}
    if not isinstance(manifest, dict):
        return STATUS_UNKNOWN, {}
    raw_skill = manifest.get("skill")
    skill = raw_skill if isinstance(raw_skill, str) and raw_skill.strip() else None
    raw_version = manifest.get("version")
    if isinstance(raw_version, int) and not isinstance(raw_version, bool) and raw_version > MANIFEST_CONTRACT_VERSION:
        return STATUS_TOO_NEW, {"skill": skill, "version": raw_version}

    allowed: set[str] = set()
    raw_deliverables = manifest.get("deliverables")
    if isinstance(raw_deliverables, list):
        allowed |= {x for x in raw_deliverables if isinstance(x, str) and x}
    else:
        raw_deliverable = manifest.get("deliverable")
        if isinstance(raw_deliverable, str) and raw_deliverable:
            allowed.add(raw_deliverable)  # geo 旧契约向后兼容
        else:
            return STATUS_UNKNOWN, {"skill": skill}
    raw_aux = manifest.get("aux_md")
    if isinstance(raw_aux, list):
        allowed |= {x for x in raw_aux if isinstance(x, str) and x}
    return STATUS_OK, {"skill": skill, "allowed": allowed, "version": raw_version}


def rebuild_hint(status: str, data: dict) -> str:
    """面向 agent 的恢复指引(按 status 与技能源定制; 供三端错误文案复用)。"""
    skill = data.get("skill")
    build_cmd = f"skills/public/{skill}/scripts/build_output.py" if skill else "管线技能的 build_output.py(geological-report 以 stdout BUILD_READY+MANIFEST_READY 为凭)"
    if status == STATUS_MISSING:
        return (
            "交付门 FAIL（bug-2225）：本线程存在交付契约（.delivery-contract）但 outputs/ 无 delivery_manifest.json——"
            f"交付 .md 必须经 {build_cmd} 产出（rc=0），禁止手工拼装 .md 交付。请先运行 build_output.py 成功后再 present_files。"
        )
    if status == STATUS_TOO_NEW:
        return (
            f"交付门 FAIL（bug-3109）：delivery_manifest.json version={data.get('version')} 高于本平台支持的契约版本 "
            f"{MANIFEST_CONTRACT_VERSION}——请升级平台, 或由 {build_cmd} 重新 build 生成本平台兼容的凭据。"
        )
    return (
        "交付门 FAIL（bug-3109）：delivery_manifest.json 无法解析或缺少 deliverables[]/deliverable 字段（未知契约）——"
        f"请重跑 {build_cmd} 修复凭据后再 present_files。"
    )
