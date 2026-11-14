"use client";

import { Bolt, FileSpreadsheet, Info, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  Badge,
  EmptyState,
  MetricCell,
  MetricStrip,
  PageHead,
  ProgressBar,
} from "@/extensions/bid-write/components/primitives";
import { projectTitle } from "@/extensions/bid-write/helpers";
import { useSelectedWriteTask } from "@/extensions/bid-write/hooks";

const TEMPLATES = [
  {
    id: "goods",
    name: "货物类标准",
    desc: "投标函 + 报价表 + 响应表 + 附件索引",
  },
  {
    id: "framework",
    name: "框架协议",
    desc: "含年度单价表与调价机制章节",
  },
  {
    id: "service",
    name: "服务类",
    desc: "含实施方案与人员配置表",
  },
] as const;

const P0_SKILLS = [
  {
    id: "bid_letter",
    name: "投标函",
    code: "bid_letter",
    count: "10 条断言 · D0 6",
  },
  {
    id: "price_sheet",
    name: "报价表",
    code: "price_sheet",
    count: "10 条断言 · D0 8",
  },
  {
    id: "response_table",
    name: "响应/偏离表",
    code: "response_table",
    count: "9 条断言 · D0 8",
  },
  {
    id: "attachment_index",
    name: "附件索引",
    code: "attachment_index",
    count: "9 条断言 · D0 5",
  },
] as const;

interface PriceRow {
  id: string;
  code: string;
  name: string;
  quantity: string;
  unit: string;
  unitPrice: string;
}

function numberValue(value: string): number {
  const parsed = Number(value.replaceAll(",", "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function money(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function GenerateView() {
  const { task } = useSelectedWriteTask();
  const [template, setTemplate] =
    useState<(typeof TEMPLATES)[number]["id"]>("goods");
  const [skills, setSkills] = useState<Record<string, boolean>>({
    bid_letter: true,
    price_sheet: true,
    response_table: true,
    attachment_index: true,
  });
  const [policy, setPolicy] = useState({
    warrantyMonths: "24",
    spareYears: "10",
    responseHours: "8",
    penaltyCap: "5",
    bidValidityDays: "90",
  });
  const [priceRows, setPriceRows] = useState<PriceRow[]>([]);

  const total = useMemo(
    () =>
      priceRows.reduce(
        (sum, row) =>
          sum + numberValue(row.quantity) * numberValue(row.unitPrice),
        0,
      ),
    [priceRows],
  );

  const addPriceRow = () => {
    setPriceRows((current) => [
      ...current,
      {
        id: `row-${Date.now()}-${current.length}`,
        code: `BOQ-${String(current.length + 1).padStart(2, "0")}`,
        name: "",
        quantity: "1",
        unit: "项",
        unitPrice: "",
      },
    ]);
  };

  const updateRow = (id: string, patch: Partial<PriceRow>) => {
    setPriceRows((current) =>
      current.map((row) => (row.id === id ? { ...row, ...patch } : row)),
    );
  };

  const selectedSkillCount = Object.values(skills).filter(Boolean).length;

  return (
    <>
      <PageHead
        icon={Bolt}
        title="③ 生成配置与执行"
        subtitle={
          task
            ? `${projectTitle(task)} · P0 四技能`
            : "P0 四技能 · 数值零幻觉：单价在输入侧录入，结果侧只读"
        }
        actions={
          <>
            <Badge tone="gray">
              模板：{TEMPLATES.find((item) => item.id === template)?.name}
            </Badge>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => toast.info("章节树预览将在生成装配器接入后开放")}
            >
              预览章节树
            </button>
          </>
        }
      />

      <MetricStrip>
        <MetricCell
          label="P0 已勾选技能"
          value={selectedSkillCount}
          suffix="/ 4"
          accent
        />
        <MetricCell label="断言注册表" value="43" suffix="条 · D0 31" />
        <MetricCell label="报价明细" value={priceRows.length} suffix="行" />
        <MetricCell
          label="含税合计"
          value={priceRows.length ? `¥${money(total)}` : "—"}
          tone="ok"
        />
      </MetricStrip>

      <div className="banner warn">
        <Info size={15} aria-hidden="true" />
        <span>
          <b>生成执行管线尚未接入：</b>
          当前页面可编辑生成配置草稿，但“开始生成”不会调用后端。
          正文、报价计算内核、断言执行与导出均需等 M1/F4
          接口落地，避免伪造生成结果。
        </span>
      </div>

      <div className="card bw-mt">
        <div className="card-h">
          <h3>模板选择</h3>
          <span className="r">
            <span className="bw-muted">货物类标准 · P0 范围</span>
          </span>
        </div>
        <div className="card-b">
          <div className="tpl">
            {TEMPLATES.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`t ${template === item.id ? "on" : ""}`}
                onClick={() => setTemplate(item.id)}
              >
                <b>{item.name}</b>
                <span>{item.desc}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card bw-mt">
        <div className="card-h">
          <h3>技能勾选</h3>
          <span className="r">
            <Badge tone="gray">断言注册表 43 条 · D0 31</Badge>
          </span>
        </div>
        <div className="card-b">
          <div className="sk bw-skill-grid">
            {P0_SKILLS.map((item) => (
              <label
                key={item.id}
                className={!skills[item.id] ? "off" : undefined}
              >
                <input
                  type="checkbox"
                  checked={skills[item.id]}
                  onChange={(event) =>
                    setSkills((current) => ({
                      ...current,
                      [item.id]: event.target.checked,
                    }))
                  }
                />
                <span>
                  <b>
                    {item.name} <span className="mono">{item.code}</span>
                  </b>
                  <span>{item.count}</span>
                </span>
              </label>
            ))}
            <label className="off">
              <input type="checkbox" disabled />
              <span>
                <b>资格文件组织</b>
                <span>P1 · 未启用</span>
              </span>
            </label>
            <label className="off">
              <input type="checkbox" disabled />
              <span>
                <b>售后承诺</b>
                <span>P1 · 未启用</span>
              </span>
            </label>
          </div>
          <div className="banner info bw-mt-sm">
            <Info size={15} aria-hidden="true" />
            <span>
              共享层 CMN 5
              条（全文占位符/绝对化/实体引用/渲染可重放/待补负证据）随导出级全文扫描自动执行，无需勾选。
            </span>
          </div>
        </div>
      </div>

      <div className="card bw-mt">
        <div className="card-h">
          <h3>承诺策略 policy</h3>
          <span className="r">
            <Badge tone="gray">本地草稿 · 不落库</Badge>
          </span>
        </div>
        <div className="card-b">
          <div className="bw-policy-grid">
            <label className="field">
              <span>质保上限（月）</span>
              <input
                className="inp"
                value={policy.warrantyMonths}
                onChange={(event) =>
                  setPolicy({ ...policy, warrantyMonths: event.target.value })
                }
              />
            </label>
            <label className="field">
              <span>备件供应年限</span>
              <input
                className="inp"
                value={policy.spareYears}
                onChange={(event) =>
                  setPolicy({ ...policy, spareYears: event.target.value })
                }
              />
            </label>
            <label className="field">
              <span>响应时限（小时）</span>
              <input
                className="inp"
                value={policy.responseHours}
                onChange={(event) =>
                  setPolicy({ ...policy, responseHours: event.target.value })
                }
              />
            </label>
            <label className="field">
              <span>违约金上限（%）</span>
              <input
                className="inp"
                value={policy.penaltyCap}
                onChange={(event) =>
                  setPolicy({ ...policy, penaltyCap: event.target.value })
                }
              />
            </label>
            <label className="field">
              <span>投标有效期（天）</span>
              <input
                className="inp"
                value={policy.bidValidityDays}
                onChange={(event) =>
                  setPolicy({ ...policy, bidValidityDays: event.target.value })
                }
              />
            </label>
          </div>
        </div>
      </div>

      <div className="card bw-mt">
        <div className="card-h">
          <h3>报价输入 · 单价表</h3>
          <span className="r">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => toast.info("CSV 导入将在计算内核接入后开放")}
            >
              <FileSpreadsheet size={13} aria-hidden="true" />
              导入 CSV
            </button>
            <button
              type="button"
              className="btn btn-sm soft"
              onClick={addPriceRow}
            >
              <Plus size={13} aria-hidden="true" />
              添加清单项
            </button>
          </span>
        </div>
        {priceRows.length === 0 ? (
          <div className="card-b">
            <EmptyState
              icon={FileSpreadsheet}
              title="暂无报价明细"
              description="报价由人工录入单价，系统只做确定性计算，不猜测价格。"
              action={
                <button type="button" className="btn pri" onClick={addPriceRow}>
                  添加第一条清单项
                </button>
              }
            />
          </div>
        ) : (
          <div className="tbl-wrap">
            <table className="tbl dense">
              <thead>
                <tr>
                  <th>清单项</th>
                  <th>名称</th>
                  <th className="num">数量</th>
                  <th>单位</th>
                  <th className="num">单价（元）</th>
                  <th className="num">合价（元）</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {priceRows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <input
                        className="inp mono bw-cell-input"
                        value={row.code}
                        onChange={(event) =>
                          updateRow(row.id, { code: event.target.value })
                        }
                      />
                    </td>
                    <td>
                      <input
                        className="inp bw-cell-input"
                        value={row.name}
                        placeholder="清单名称"
                        onChange={(event) =>
                          updateRow(row.id, { name: event.target.value })
                        }
                      />
                    </td>
                    <td>
                      <input
                        className="inp num bw-cell-input"
                        value={row.quantity}
                        onChange={(event) =>
                          updateRow(row.id, { quantity: event.target.value })
                        }
                      />
                    </td>
                    <td>
                      <input
                        className="inp bw-cell-input"
                        value={row.unit}
                        onChange={(event) =>
                          updateRow(row.id, { unit: event.target.value })
                        }
                      />
                    </td>
                    <td>
                      <input
                        className="inp num bw-cell-input"
                        value={row.unitPrice}
                        placeholder="0.00"
                        onChange={(event) =>
                          updateRow(row.id, { unitPrice: event.target.value })
                        }
                      />
                    </td>
                    <td className="num mono">
                      {money(
                        numberValue(row.quantity) * numberValue(row.unitPrice),
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm"
                        aria-label={`删除 ${row.code}`}
                        onClick={() =>
                          setPriceRows((current) =>
                            current.filter((item) => item.id !== row.id),
                          )
                        }
                      >
                        <Trash2 size={13} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={5} className="num bw-total-label">
                    合计（本地草稿）
                  </td>
                  <td className="num mono bw-total-value">¥{money(total)}</td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
        )}
        <div className="card-b">
          <p className="bw-muted">
            金额只按已录入数量 ×
            单价计算；最高限价、税率、四舍五入与跨表一致性校验需由计算内核执行。
          </p>
        </div>
      </div>

      <div className="card bw-mt">
        <div className="card-h">
          <h3>分册与签章</h3>
          <span className="r">
            <Badge tone="gray">正本 1 · 副本 4 · 电子 1</Badge>
            <Badge tone="gray">页码：连续</Badge>
            <Badge tone="gray">CA 签章位：预留</Badge>
          </span>
        </div>
        <div className="card-b">
          <div className="bw-generate-actions">
            <button
              type="button"
              className="btn pri"
              onClick={() =>
                toast.error("生成执行管线尚未接入，未调用后端生成")
              }
            >
              开始生成
            </button>
            <span className="bw-muted">解析 → 装配 → 逐节生成 → 断言校验</span>
          </div>
          <div className="bw-gen-list">
            {P0_SKILLS.map((item) => (
              <div className="gen-row" key={item.id}>
                <b>{item.name}</b>
                <div>
                  <ProgressBar value={0} />
                  <div className="gen-sub">
                    待执行 · 需要生成服务与断言执行器
                  </div>
                </div>
                <Badge tone="gray">未开始</Badge>
              </div>
            ))}
          </div>
        </div>
      </div>

      {!task ? (
        <div className="banner info bw-mt">
          <Info size={15} aria-hidden="true" />
          <span>
            当前没有选中任务；生成配置草稿仍可编辑，但不会关联到任何项目。
            请先在项目列表创建写作项目。
          </span>
        </div>
      ) : null}
    </>
  );
}
