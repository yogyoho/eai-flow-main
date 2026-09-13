# tests/fixtures — 3218 脱敏 fixture

本目录存放 v2 管线的回归 fixture：`sample3218_digest.json`（入库）与一次性构建工具 `build_fixture.py`。

## 生成命令（host 一次性运行）

```bash
cd skills/public/coal-mine-tunneling-regulation
PYTHONUTF8=1 ../../../backend/.venv/Scripts/python.exe tests/fixtures/build_fixture.py \
  "D:/18 辽宁创元/03 项目策划/01 中煤科工/3218运输顺槽掘进作业规程.docx"
# 期望: FIXTURE_READY: ... chapters: 10 （front + ch1..ch9）
```

CI 无样例文件时不需重建——`sample3218_digest.json` 已入库，测试直接读 fixture。

## 脱敏规则

源 docx 为真实项目作业规程，**源文件绝不入库**（含于本机用户目录，未加入 git）。入库的 digest 只含统计量与种子值，已按下列规则脱敏：

| 原文实体 | 脱敏替换 |
|---|---|
| 矿名/集团名 | 某矿 / 某集团 |
| 规程编号 | 掘ZJED-…（编号格式保留、单位代码脱敏） |
| 队组名 | 综掘某队 |
| 避灾路线中的井巷系统名 | 轨道大巷/胶带大巷/副井底 等通用名 |

**数值全部保留**（长度 902.236m、断面 18/15m²、瓦斯 3.4/2.45/1.39、涌水量、锚杆锚索规格等）——它们是表单种子（`form_seed`）与章级深度门（`eff_chars`）的回归基准。矿名与队组名之外，工作面编号以 N 前缀形式保留（N3218）。

`form_seed` 与 `references/stages/tunneling.json` 存在互锁约束：**各族种子字段 ⊇ 该族全部 required 字段**。修改 tunneling.json 的 required 集后须重跑生成命令并过断言（含 ×1.2 总量门，见计划 Task 4 Step 2）。

## 集成测试的门（真实 docx 在场才跑）

需要真实源 docx 的集成测试沿 fire-protection `test_integration.py`（L11-18）模式：

```python
SAMPLE = Path(os.environ.get("TUNNELING_SAMPLE_DOCX",
    r"D:/18 辽宁创元/03 项目策划/01 中煤科工/3218运输顺槽掘进作业规程.docx"))
pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample docx not present")
```

- 环境变量 `TUNNELING_SAMPLE_DOCX` 覆盖默认本机路径；
- 样例不在场（CI / 他机）→ 整文件 skip，单元测试只依赖入库的 `sample3218_digest.json`。

## 章级深度实测（fixture 构建时产出）

`chapters` 记录源样例每章 effective_chars（算法对齐 `scripts/build_output.py::effective_chars`：剔空行/标题行/表格行、剔行内 `[\s|\-#*:]` 装饰符）与表格数，供 v2 管线设定章级深度目标与 J7 试算门对账。
