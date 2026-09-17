"use client";

/** Seed 规则编辑抽屉: 7 角色锚点编辑(候选=OCR 表头单元格 + 自由输入)。
 * 两个入口共用: 配置tab新建/编辑 + 合同解析tab未匹配表"生成规则草稿"。 */

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TableSeed } from "@/extensions/contract-price/types";

export const SEED_ROLES = [
  { key: "name", label: "货物名称列", required: true },
  { key: "spec", label: "规格/参数列", required: false },
  { key: "qty", label: "数量列", required: false },
  { key: "unit", label: "单位列", required: false },
  { key: "price_unit", label: "含税单价列", required: true },
  { key: "price_total", label: "合价列", required: false },
  { key: "price_untaxed", label: "不含税单价列", required: false },
] as const;

export type SeedDraft = TableSeed;

export function emptySeed(): SeedDraft {
  return {
    id: "",
    display_name: "",
    title_keywords: [],
    columns: { name: [], spec: [], qty: [], unit: [], price_unit: [], price_total: [], price_untaxed: [] },
    exclude: { price_unit: ["不含税"] },
    source: null,
  };
}

/** 草稿建议: 内置 token 优先级表对表头做一次性子串映射(确定性,无后端往返)。 */
const DRAFT_TOKENS: Record<string, string[]> = {
  name: ["项目名称", "品名", "物资名称", "货物名称", "名称", "材质"],
  spec: ["规格型号", "材质规格", "规格", "材质", "参数"],
  qty: ["工程量", "暂定数量", "调整数量", "数量"],
  unit: ["计量单位", "单位"],
  price_unit: ["含税单价", "综合单价", "含税落地单价", "调整后单价"],
  price_total: ["含税合价", "含税总价", "总金额", "调整后合价"],
  price_untaxed: ["不含税单价"],
};

export function draftFromHeader(headerCells: string[], title = ""): SeedDraft {
  const seed = emptySeed();
  seed.display_name = title || "新表格规则";
  const used = new Set<number>();
  for (const { key } of SEED_ROLES) {
    for (const token of DRAFT_TOKENS[key] ?? []) {
      const ci = headerCells.findIndex(
        (h, i) => !used.has(i) && h && h.includes(token) && !(key === "price_unit" && h.includes("不含税")),
      );
      if (ci >= 0) {
        const cell = headerCells[ci];
        if (cell) {
          seed.columns[key] = [cell];
          used.add(ci);
          break;
        }
      }
    }
  }
  return seed;
}

interface Props {
  open: boolean;
  seed: SeedDraft | null;
  headerCells?: string[]; // 有值=从未匹配表起草:角色下拉候选为这些表头
  saving?: boolean;
  onClose: () => void;
  onSave: (seed: SeedDraft) => void;
}

export function SeedEditorDrawer({ open, seed, headerCells, saving, onClose, onSave }: Props) {
  const [draft, setDraft] = useState<SeedDraft | null>(seed);

  useEffect(() => setDraft(seed), [seed]);

  const candidates = useMemo(
    () =>
      Array.from(new Set([...(headerCells ?? []), ...(draft ? Object.values(draft.columns).flat() : [])])).filter(
        Boolean,
      ),
    [headerCells, draft],
  );
  if (!open || !draft) return null;

  const set = (patch: Partial<SeedDraft>) => setDraft({ ...draft, ...patch });
  const setCol = (role: keyof SeedDraft["columns"], text: string) =>
    set({
      columns: {
        ...draft.columns,
        [role]: text
          .split(/[,，、\n]/)
          .map((s) => s.trim())
          .filter(Boolean),
      },
    });

  const valid =
    draft.id.trim() &&
    draft.display_name.trim() &&
    draft.columns.name.length > 0 &&
    (draft.columns.price_unit.length > 0 || draft.columns.price_total.length > 0);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-[520px] max-w-[92vw] overflow-y-auto border-l bg-background p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">{seed?.id ? "编辑定位规则" : "新建定位规则"}</h2>
          <Button size="icon" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm font-medium">规则 ID *</label>
              <Input value={draft.id} disabled={!!seed?.id} placeholder="如 gcl-qd" onChange={(e) => set({ id: e.target.value })} />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">规则名称 *</label>
              <Input
                value={draft.display_name}
                placeholder="如 工程量清单计价表"
                onChange={(e) => set({ display_name: e.target.value })}
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium">表名关键词（逗号分隔,仅用于多规则消歧）</label>
            <Input
              value={draft.title_keywords.join("，")}
              placeholder="工程量清单，清单计价"
              onChange={(e) =>
                set({ title_keywords: e.target.value.split(/[,，\n]/).map((s) => s.trim()).filter(Boolean) })
              }
            />
          </div>

          <div className="rounded-lg border p-3">
            <div className="mb-2 text-sm font-medium">列锚点（子串匹配;多个用逗号分隔）</div>
            <div className="space-y-2">
              {SEED_ROLES.map(({ key, label, required }) => (
                <div key={key} className="grid grid-cols-[110px_1fr] items-center gap-2">
                  <label className="text-xs text-muted-foreground">
                    {label}
                    {required ? " *" : ""}
                  </label>
                  {headerCells && headerCells.length > 0 ? (
                    <Select
                      value={draft.columns[key][0] ?? ""}
                      onValueChange={(v) => setCol(key, v)}
                    >
                      <SelectTrigger className="h-8">
                        <SelectValue placeholder="选表头列" />
                      </SelectTrigger>
                      <SelectContent>
                        {candidates.map((h) => (
                          <SelectItem key={h} value={h}>
                            {h}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      className="h-8"
                      value={draft.columns[key].join("，")}
                      onChange={(e) => setCol(key, e.target.value)}
                    />
                  )}
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              锚点按归一化子串匹配（忽略空格/（…）括注/全半角）。「不含税」列自动排除出含税单价。
            </p>
          </div>
        </div>

        <div className="mt-6 flex items-center gap-3">
          <Button disabled={!valid || saving} onClick={() => onSave(draft)}>
            {saving ? "保存中…" : "保存规则"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          {!valid && <span className="text-xs text-muted-foreground">需规则ID、名称、货物名称列、至少一个价格列</span>}
        </div>
      </div>
    </div>
  );
}
