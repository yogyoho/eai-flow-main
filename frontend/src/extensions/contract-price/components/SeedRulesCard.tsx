"use client";

/** Seed 规则卡片列表: 展示/新建/编辑/删除 + 命中统计(parse_meta.matched_seeds 聚合)。 */

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  SeedEditorDrawer,
  emptySeed,
  type SeedDraft,
} from "@/extensions/contract-price/components/SeedEditorDrawer";
import { useDocuments } from "@/extensions/contract-price/hooks";
import type { TableSeed } from "@/extensions/contract-price/types";

interface Props {
  seeds: TableSeed[];
  onChange: (seeds: TableSeed[]) => void;
  saving?: boolean;
}

export function SeedRulesCard({ seeds, onChange, saving }: Props) {
  const [editing, setEditing] = useState<SeedDraft | null>(null);
  const { data } = useDocuments({ limit: 200 });
  // 命中统计: 聚合各文档 parse_meta.matched_seeds(seed名→表数)
  const hits = useMemo(() => {
    const acc: Record<string, number> = {};
    for (const d of data?.items ?? []) {
      const ms = (
        d.parse_meta as { matched_seeds?: Record<string, number> } | null
      )?.matched_seeds;
      for (const [k, v] of Object.entries(ms ?? {}))
        acc[k] = (acc[k] ?? 0) + (v ?? 0);
    }
    return acc;
  }, [data]);

  const save = (s: SeedDraft) => {
    const exists = seeds.some((x) => x.id === s.id);
    onChange(
      exists ? seeds.map((x) => (x.id === s.id ? s : x)) : [...seeds, s],
    );
    setEditing(null);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>表格定位规则（Seed）</CardTitle>
            <CardDescription>
              解析时按规则定位分项价格表并锚定列;未匹配任何规则的表不提取,可在「合同解析」页为其新建规则后重解析。
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setEditing(emptySeed())}>
            <Plus className="h-4 w-4" /> 新建规则
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {seeds.map((s) => {
          const hitCount = hits[s.display_name] ?? 0;
          return (
            <div
              key={s.id}
              className="flex items-center justify-between rounded-lg border p-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">
                    {s.display_name}
                  </span>
                  {hitCount > 0 ? (
                    <Badge variant="secondary" className="shrink-0">
                      命中 {hitCount} 表
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="text-muted-foreground shrink-0"
                    >
                      未命中
                    </Badge>
                  )}
                </div>
                <div className="text-muted-foreground mt-1 truncate text-xs">
                  {[s.columns.name, s.columns.price_unit, s.columns.price_total]
                    .flat()
                    .filter(Boolean)
                    .join(" / ")}
                  {s.source ? ` · ${s.source}` : ""}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => setEditing({ ...s })}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="text-destructive"
                  onClick={() => onChange(seeds.filter((x) => x.id !== s.id))}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          );
        })}
        {seeds.length === 0 && (
          <p className="text-muted-foreground py-6 text-center text-sm">
            暂无规则——解析将无法提取任何表格。保存后系统会自动恢复内置规则库。
          </p>
        )}
      </CardContent>
      <SeedEditorDrawer
        open={editing !== null}
        seed={editing}
        saving={saving}
        onClose={() => setEditing(null)}
        onSave={save}
      />
    </Card>
  );
}
