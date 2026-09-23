"use client";

/** 自进化候选卡（⑥ 落地工作流，补遗 2026-09-22）：
 *  列出 pending 的字段修正证据（recurrence 降序）+ 该文档 L4 建议锚词。
 *  操作路径：照证据在上方种子规则卡加/改锚词并保存 → 回来「已落规则卡」标记晋升；
 *  误操作/不具代表性则「忽略」（dismissed 永不重开）。 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { contractPriceApi } from "@/extensions/contract-price/api";

const FIELD_LABELS: Record<string, string> = {
  contract_no: "合同编号",
  supplier: "供应商",
  sign_date: "签订日期",
  project_name: "项目名称",
  project_location: "项目所在地",
  project_no: "项目编号",
  goods_name: "货物名称",
  spec_model: "规格型号",
  unit_price: "含税单价",
  tech_params: "技术参数",
};

const ERROR_LABELS: Record<string, string> = {
  missed: "漏提",
  cleared: "清空",
  "digit-transposed": "数字错位",
  "digit-split": "粘连/断开",
  "digit-drift": "数字漂移",
  variant: "命名变体",
  "unit-affixed": "单位缀",
  other: "其他",
};

export function EvolutionCandidatesCard() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["cpa-evolution-candidates"],
    queryFn: contractPriceApi.evolutionCandidates,
    staleTime: 30_000,
  });
  const items = data?.items ?? [];

  const act = (fn: (id: string) => Promise<unknown>) => async (id: string) => {
    await fn(id);
    await queryClient.invalidateQueries({
      queryKey: ["cpa-evolution-candidates"],
    });
  };
  const onAdopt = act(contractPriceApi.adoptEvolutionCandidate);
  const onDismiss = act(contractPriceApi.dismissEvolutionCandidate);

  if (isLoading || items.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4" />
          自进化 · 修正候选
        </CardTitle>
        <CardDescription>
          这些字段被人工反复纠正——照证据在上方种子规则卡补锚词并保存后标记晋升；
          误操作可忽略。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((c) => (
          <div
            key={c.learning_id}
            className="border-border flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-3 py-2 text-sm"
          >
            <span className="font-medium">
              {FIELD_LABELS[c.field] ?? c.field}
            </span>
            {c.error_pattern ? (
              <span className="text-muted-foreground text-xs">
                {ERROR_LABELS[c.error_pattern] ?? c.error_pattern}
              </span>
            ) : null}
            <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs">
              ×{c.recurrence}
            </span>
            <span className="text-muted-foreground min-w-0 flex-1 break-all font-mono text-xs">
              {c.evidence}
            </span>
            {Object.keys(c.suggested_anchors ?? {}).length > 0 ? (
              <span className="text-muted-foreground text-xs">
                L4建议锚词：
                {Object.entries(c.suggested_anchors)
                  .map(([role, words]) => `${role}: ${words.join("/")}`)
                  .join("；")}
              </span>
            ) : null}
            <span className="ml-auto flex shrink-0 gap-1.5">
              <Button size="sm" variant="outline" onClick={() => onDismiss(c.learning_id)}>
                忽略
              </Button>
              <Button size="sm" onClick={() => onAdopt(c.learning_id)}>
                已落规则卡
              </Button>
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
