/**
 * 03 实体库骨架页（EAI-CUSTOM）：过滤条 + 实体表 + 分页（静态示例数据）。
 * 设计稿 docs/designs/ontostudio-frontend-design.html；真实数据面待 kernel P2（实体查询 API）。
 */
import { Database } from "lucide-react";

import { DemoTag, PageHeader, Panel } from "@/pages/shared";

type Row = {
  name: string;
  etype: string;
  norm: string;
  confidence: number;
  status: "active" | "pending_review" | "merged";
  mentions: number;
  updated: string;
};

const ROWS: Row[] = [
  { name: "横城煤矿项目", etype: "project", norm: "横城煤矿项目", confidence: 0.96, status: "active", mentions: 17, updated: "09-18 10:12" },
  { name: "山西煤机集团", etype: "org", norm: "山西煤机集团", confidence: 0.94, status: "active", mentions: 23, updated: "09-18 10:32" },
  { name: "山西煤矿机械制造有限公司", etype: "org", norm: "山西煤机集团", confidence: 0.91, status: "merged", mentions: 8, updated: "09-18 10:32" },
  { name: "矿用刮板输送机 SGZ-800", etype: "goods", norm: "矿用刮板输送机", confidence: 0.88, status: "active", mentions: 11, updated: "09-17 16:40" },
  { name: "煤矿设备安装一级资质", etype: "qualification", norm: "煤矿设备安装资质", confidence: 0.93, status: "active", mentions: 14, updated: "09-17 16:02" },
  { name: "桑干河饮用水源保护区", etype: "place", norm: "桑干河水源保护区", confidence: 0.79, status: "pending_review", mentions: 6, updated: "09-17 14:28" },
];

const STATUS_TONE = {
  active: "text-primary",
  pending_review: "text-warning",
  merged: "text-destructive",
} as const;

function FilterSelect({ label }: { label: string }) {
  return (
    <select
      aria-label={label}
      className="border-input bg-card focus:border-primary h-9 rounded-md border px-3 text-sm shadow-xs outline-none"
    >
      <option>{label}</option>
    </select>
  );
}

export function EntitiesPage() {
  return (
    <div className="p-6">
      <PageHeader
        clause="03 · 实体"
        icon={ Database }
        title="实体库"
        description="点击任意行打开实体抽屉：属性、证据链与合并历史（骨架：数据面待 kernel P2）"
        actions={
          <>
            <button className="border-border bg-card hover:bg-accent h-9 rounded-md border px-4 text-sm font-medium shadow-xs">
              导出当前视图
            </button>
            <button className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 rounded-md px-4 text-sm font-medium">
              手工录入实体
            </button>
          </>
        }
      />
      <Panel>
        <div className="flex flex-wrap items-center gap-2 px-4 py-3">
          <FilterSelect label="全部类型" />
          <FilterSelect label="全部状态" />
          <FilterSelect label="置信度 ≥ 0.7" />
          <span className="text-muted-foreground ml-auto text-xs">
            共 1,284 条 · 命中 <b className="text-primary">36</b> <DemoTag />
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-border bg-muted/50 border-b">
                {["实体名称", "类型", "规范化名", "置信度", "状态", "证据", "更新时间"].map(
                  (head, index) => (
                    <th
                      key={head}
                      className={`text-muted-foreground px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap ${index >= 3 && index <= 5 ? "text-right" : "text-left"}`}
                    >
                      {head}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {ROWS.map((row) => (
                <tr
                  key={row.name}
                  className="hover:bg-muted/50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-medium">{row.name}</td>
                  <td className="px-4 py-3">
                    <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-[11px]">
                      {row.etype}
                    </span>
                  </td>
                  <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                    {row.norm}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {row.confidence.toFixed(2)}
                  </td>
                  <td className={`px-4 py-3 text-xs font-medium ${STATUS_TONE[row.status]}`}>
                    {row.status}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{row.mentions}</td>
                  <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                    {row.updated}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text-muted-foreground flex items-center gap-2 px-4 py-3 text-xs">
          <span>每页 20 条</span>
          <span className="border-border bg-card shadow-xs grid h-7 min-w-7 place-items-center rounded-md border">
            ‹
          </span>
          <span className="bg-primary text-primary-foreground grid h-7 min-w-7 place-items-center rounded-md">
            1
          </span>
          <span className="border-border bg-card shadow-xs grid h-7 min-w-7 place-items-center rounded-md border">
            2
          </span>
          <span className="border-border bg-card shadow-xs grid h-7 min-w-7 place-items-center rounded-md border">
            ›
          </span>
        </div>
      </Panel>
    </div>
  );
}
