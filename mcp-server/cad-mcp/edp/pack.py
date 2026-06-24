"""Domain pack loading: manifest + symbols + frame templates.

A pack lives at <domains_root>/<domain>/{manifest.json, symbols/*.json,
frame_templates/*.json}. Loaded by domain name; the composer never imports
domain code — packs are declarative assets. Optional rules.py hooks are M2.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SymbolSpec:
    """A symbol = primitives (op list) + anchor + ports + label anchor.

    The op vocabulary is shared across all packs (see strategies._draw_primitive).
    `ports` are consumed only by the schematic strategy (P&ID edge routing).
    """

    type: str
    insertion_base: tuple[float, float]
    default_layer: str
    default_size_mm: float
    primitives: list[dict]
    ports: list[dict] = field(default_factory=list)
    label_anchor: tuple[float, float] | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "SymbolSpec":
        ib = d.get("insertion_base", [0, 0])
        la = d.get("label_anchor")
        return cls(
            type=d["type"],
            insertion_base=(float(ib[0]), float(ib[1])),
            default_layer=d.get("default_layer", "0"),
            default_size_mm=float(d.get("default_size_mm", 0) or 0),
            primitives=list(d.get("primitives", [])),
            ports=list(d.get("ports", [])),
            label_anchor=(float(la[0]), float(la[1])) if la else None,
        )


@dataclass
class SymbolLib:
    specs: dict[str, SymbolSpec]

    def resolve(self, type_name: str) -> SymbolSpec | None:
        return self.specs.get(type_name)


@dataclass
class Pack:
    domain: str
    drawing_types: dict  # name → {strategy, frame, scale_default, ...}
    layers: dict  # name → {color, ...}
    symbols: SymbolLib
    frame_templates: dict  # name → frame spec dict


def load_pack(domain: str, domains_root: Path) -> Pack | None:
    """Load a pack by domain name. Returns None if the domain dir/manifest is absent."""
    root = Path(domains_root) / domain
    manifest_p = root / "manifest.json"
    if not manifest_p.exists():
        return None
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))

    specs: dict[str, SymbolSpec] = {}
    sym_glob = manifest.get("symbols_glob", "symbols/*.json")
    for sp in sorted(root.glob(sym_glob)):
        sd = json.loads(sp.read_text(encoding="utf-8"))
        specs[sd["type"]] = SymbolSpec.from_dict(sd)

    frames: dict[str, dict] = {}
    ft_dir = root / "frame_templates"
    if ft_dir.is_dir():
        for fp in sorted(ft_dir.glob("*.json")):
            fd = json.loads(fp.read_text(encoding="utf-8"))
            frames[fd["name"]] = fd

    return Pack(
        domain=manifest.get("domain", domain),
        drawing_types=manifest.get("drawing_types", {}),
        layers=manifest.get("layers", {}),
        symbols=SymbolLib(specs),
        frame_templates=frames,
    )
