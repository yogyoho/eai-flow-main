"""Engineering Drawing Platform — domain-agnostic core.

compose(intent, domains_root) loads the domain pack, dispatches to the
strategy declared for the drawing type, renders annotations + frame, and
validates. Knows nothing about roadways or pumps — only type→symbol and
placement.kind→strategy. See PLATFORM_SPEC.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from .pack import load_pack
from .render import new_doc, render_annotations, render_frame
from .strategies import STRATEGIES
from .validate import validate


class ComposeError(Exception):
    """Raised for known, reportable compose failures (code + detail)."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(detail or code)


def _merged_layers(pack_layers: dict, intent_layers: list[dict]) -> dict:
    """Pack default layers, overridden/appended by intent.layers (list of {name,...})."""
    layers = {name: dict(attrs or {}) for name, attrs in (pack_layers or {}).items()}
    for layer in intent_layers or []:
        name = layer.get("name")
        if not name:
            continue
        layers[name] = {k: v for k, v in layer.items() if k != "name"}
    return layers


def compose(intent: dict, domains_root: Path):
    """Render an intent into an ezdxf doc + RenderReport + validations.

    Returns (doc, report, validations). Raises ComposeError(code) for
    unknown_domain / unknown_drawing_type / unknown_strategy / schema_invalid.
    """
    if not isinstance(intent, dict):
        raise ComposeError("schema_invalid", "intent must be a JSON object")
    domain = intent.get("domain")
    drawing_type = intent.get("drawing_type")
    if not domain or not drawing_type:
        raise ComposeError("schema_invalid", f"need domain + drawing_type, got domain={domain!r} drawing_type={drawing_type!r}")

    pack = load_pack(domain, Path(domains_root))
    if pack is None:
        raise ComposeError("unknown_domain", f"no pack at {domains_root}/{domain}")

    dtype = pack.drawing_types.get(drawing_type)
    if not dtype:
        raise ComposeError("unknown_drawing_type", f"{drawing_type!r} not declared in domain {domain!r}")

    strategy_name = dtype.get("strategy")
    strategy = STRATEGIES.get(strategy_name)
    if strategy is None:
        raise ComposeError("unknown_strategy", f"strategy {strategy_name!r} not implemented (declared for {drawing_type!r})")

    layers = _merged_layers(pack.layers, intent.get("layers", []))
    doc, msp = new_doc(layers)

    report = strategy(msp, intent.get("entities", []), pack.symbols, layers)
    render_annotations(msp, intent.get("annotations", []))
    frame_spec = pack.frame_templates.get(dtype.get("frame"))
    render_frame(msp, frame_spec, intent.get("title_block"))

    validations = validate(intent, report, msp, pack)
    return doc, report, validations


def compose_from_json(intent_json: str | dict, domains_root: Path):
    """Convenience: accept intent as a JSON string or an already-parsed dict."""
    if isinstance(intent_json, (bytes, bytearray)):
        intent_json = intent_json.decode("utf-8")
    if isinstance(intent_json, str):
        try:
            intent = json.loads(intent_json)
        except json.JSONDecodeError as exc:
            raise ComposeError("schema_invalid", f"intent_json is not valid JSON: {exc}") from exc
    else:
        intent = intent_json
    return compose(intent, domains_root)
