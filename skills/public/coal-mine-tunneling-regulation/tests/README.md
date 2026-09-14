# 测试

运行（技能根为 cwd）：`cd skills/public/coal-mine-tunneling-regulation && PYTHONUTF8=1 python -m pytest tests/ -v`

- 全部 stdlib-only + pytest，不 import backend/deerflow，不进 CI（backend make test 只收 backend/tests/）。
- fixtures/sample3218_digest.json 为 3218 样例脱敏产物（数值保留供回归；重建：`python tests/fixtures/build_fixture.py <docx路径>`，源文件不入库）。
- **form_seed 的 array<object> 字段是散文摘要非 schema 形态**（如 bolt_specs="Φ22×2400mm…"）——需要元素键级结构的测试须扩展 build_fixture 另建（见 test_contracts._setup 的 profile 族用法）。
- 涉及真实样本的用例：`TUNNELING_SAMPLE_DOCX` 环境变量 + skipif 门，无样本环境全跳过。
- calibrate.py / bank_compile.py 为二期 dormant 件：零调用点，二期启用条件=掘进规程样例 ≥5 份（先做节标题规范化清洗，否则 calibrate 必 rc=1 零切片）。
