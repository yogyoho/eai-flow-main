"""测试套件共享脚手架：把技能 scripts/ 注入 sys.path（沿 test_ingest_bug3229 L20-23 先例）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
