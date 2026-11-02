"""金标准题库契约(EAI-CUSTOM 2026-11-03,spec §5/§6)。Expectation.verdict 缺省
violation:need_human 类断言须显式 verdict: need_human——漏报判定按 verdict 分桶,
引擎降级链(need_human)不冒充命中。strict 的「期望外」只数 verdict=violation
(need_human 是引擎主动声明无法判定,不是错判;其断言走 expect_issues 显式期待)。"""

from dataclasses import dataclass, field


@dataclass
class Expectation:
    rule_id: str
    severity: str
    contains: list[str] = field(default_factory=list)
    verdict: str = "violation"  # violation | need_human | unclear
    entity: str = ""  # 实体消歧子串(对 entity_keys+message;L2 逐实体多条时必带,spec §1.5)
    acceptable_rule_ids: list[str] = field(default_factory=list)  # 等价规则集:任一命中算 TP(不计覆盖率地板,spec §1.5)


@dataclass
class ChecklistExpect:
    unknown_count: int = 0
    status_by_no: dict[str, str] = field(default_factory=dict)  # {no: MATCHED|PARTIAL|MISSING|UNKNOWN}


@dataclass
class GoldenCase:
    case: str
    desc: str
    fields: dict
    expect_issues: list[Expectation]
    expect_absent: list[str]
    strict: bool = False
    checklist: ChecklistExpect | None = None
    model_script: dict[str, str] = field(default_factory=dict)  # {rule_id: verdicts JSON}
    source_path: str = ""


@dataclass
class CaseResult:
    case: str
    desc: str
    strict: bool
    ok: bool
    missing: list[str]  # 期望未命中渲染
    unexpected: list[str]  # strict 下期望外 violation
    absent_violations: list[str]  # expect_absent 违例
    checklist_diff: list[str]
    hits: dict[str, int] = field(default_factory=dict)  # {rule_id: 命中数}(成绩单 tp 来源)
    n_issues: int = 0

    @property
    def diff_lines(self) -> list[str]:
        return [*self.missing, *self.unexpected, *self.absent_violations, *self.checklist_diff]
