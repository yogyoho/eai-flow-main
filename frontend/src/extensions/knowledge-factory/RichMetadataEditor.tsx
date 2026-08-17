"use client";

import {
  ChevronRight,
  ChevronDown,
  Plus,
  Trash2,
  Table as TableIcon,
  Image,
  FunctionSquare,
  Cog,
  Ruler,
} from "lucide-react";
import React, { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { EditorSection } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface Props {
  section: EditorSection;
  onChange: (updates: Partial<EditorSection>) => void;
}

export function RichMetadataEditor({ section, onChange }: Props) {
  // 默认全部展开（用户可手动折叠）
  const [openMap, setOpenMap] = useState<Record<string, boolean>>({
    tables: true,
    figures: true,
    formulas: true,
    calc: true,
    profile: true,
  });
  const toggle = (key: string) =>
    setOpenMap((prev) => ({ ...prev, [key]: !prev[key] }));

  const update = (field: keyof Props["section"], value: unknown) =>
    onChange({ [field]: value } as Partial<EditorSection>);

  return (
    <div className="mt-3 space-y-2">
      {/* 📊 Table Schemas */}
      <CollapsibleCard
        icon={TableIcon}
        label="表格定义"
        color="text-blue-500"
        count={section.tableSchemas?.length ?? 0}
        open={openMap.tables ?? false}
        onToggle={() => toggle("tables")}
      >
        {(section.tableSchemas ?? []).map((t, i) => (
          <ItemRow
            key={i}
            onDelete={() =>
              update(
                "tableSchemas",
                (section.tableSchemas ?? []).filter((_, j) => j !== i),
              )
            }
          >
            <Input
              value={t.table_id}
              placeholder="table_id"
              className="h-7 w-24 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "tableSchemas",
                  i,
                  { table_id: e.target.value },
                  onChange,
                )
              }
            />
            <Input
              value={t.caption}
              placeholder="表格标题"
              className="h-7 flex-1 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "tableSchemas",
                  i,
                  { caption: e.target.value },
                  onChange,
                )
              }
            />
            <span className="text-muted-foreground shrink-0 text-xs">
              {t.columns.length}列
            </span>
          </ItemRow>
        ))}
        <AddButton
          onClick={() =>
            update("tableSchemas", [
              ...(section.tableSchemas ?? []),
              {
                table_id: "",
                caption: "",
                columns: [{ header: "", width: "", type: "string", unit: "" }],
                data_source: "template",
                required: true,
              },
            ])
          }
        />
      </CollapsibleCard>

      {/* 📷 Figure Requirements */}
      <CollapsibleCard
        icon={Image}
        label="图片需求"
        color="text-green-500"
        count={section.figureRequirements?.length ?? 0}
        open={openMap.figures ?? false}
        onToggle={() => toggle("figures")}
      >
        {(section.figureRequirements ?? []).map((f, i) => (
          <ItemRow
            key={i}
            onDelete={() =>
              update(
                "figureRequirements",
                (section.figureRequirements ?? []).filter((_, j) => j !== i),
              )
            }
          >
            <Input
              value={f.figure_id}
              placeholder="figure_id"
              className="h-7 w-24 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "figureRequirements",
                  i,
                  { figure_id: e.target.value },
                  onChange,
                )
              }
            />
            <Input
              value={f.caption}
              placeholder="图片标题"
              className="h-7 flex-1 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "figureRequirements",
                  i,
                  { caption: e.target.value },
                  onChange,
                )
              }
            />
            <Input
              value={f.suggested_type}
              placeholder="类型"
              className="h-7 w-20 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "figureRequirements",
                  i,
                  { suggested_type: e.target.value },
                  onChange,
                )
              }
            />
          </ItemRow>
        ))}
        <AddButton
          onClick={() =>
            update("figureRequirements", [
              ...(section.figureRequirements ?? []),
              {
                figure_id: "",
                caption: "",
                suggested_type: "image",
                placement_section: "",
                required: false,
                fallback: "",
              },
            ])
          }
        />
      </CollapsibleCard>

      {/* 📐 Formula References */}
      <CollapsibleCard
        icon={FunctionSquare}
        label="公式引用"
        color="text-purple-500"
        count={section.formulaReferences?.length ?? 0}
        open={openMap.formulas ?? false}
        onToggle={() => toggle("formulas")}
      >
        {(section.formulaReferences ?? []).map((f, i) => (
          <ItemRow
            key={i}
            onDelete={() =>
              update(
                "formulaReferences",
                (section.formulaReferences ?? []).filter((_, j) => j !== i),
              )
            }
          >
            <Input
              value={f.formula_id}
              placeholder="公式编号"
              className="h-7 w-28 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "formulaReferences",
                  i,
                  { formula_id: e.target.value },
                  onChange,
                )
              }
            />
            <Input
              value={f.name}
              placeholder="公式名称"
              className="h-7 flex-1 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "formulaReferences",
                  i,
                  { name: e.target.value },
                  onChange,
                )
              }
            />
          </ItemRow>
        ))}
        <AddButton
          onClick={() =>
            update("formulaReferences", [
              ...(section.formulaReferences ?? []),
              {
                formula_id: "",
                name: "",
                applicable_section: "",
                expression: "",
                input_vars: [],
              },
            ])
          }
        />
      </CollapsibleCard>

      {/* ⚙️ Calc Script Bindings */}
      <CollapsibleCard
        icon={Cog}
        label="计算脚本"
        color="text-orange-500"
        count={section.calcScriptBindings?.length ?? 0}
        open={openMap.calc ?? false}
        onToggle={() => toggle("calc")}
      >
        {(section.calcScriptBindings ?? []).map((c, i) => (
          <ItemRow
            key={i}
            onDelete={() =>
              update(
                "calcScriptBindings",
                (section.calcScriptBindings ?? []).filter((_, j) => j !== i),
              )
            }
          >
            <Input
              value={c.script}
              placeholder="脚本路径"
              className="h-7 flex-1 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "calcScriptBindings",
                  i,
                  { script: e.target.value },
                  onChange,
                )
              }
            />
            <Input
              value={c.section}
              placeholder="小节"
              className="h-7 w-20 text-xs"
              onChange={(e) =>
                editItem(
                  section,
                  "calcScriptBindings",
                  i,
                  { section: e.target.value },
                  onChange,
                )
              }
            />
            <span
              className={cn(
                "rounded px-1.5 py-0.5 text-xs",
                c.trigger === "auto"
                  ? "bg-green-100 text-green-700"
                  : "bg-gray-100 text-gray-600",
              )}
            >
              {c.trigger}
            </span>
          </ItemRow>
        ))}
        <AddButton
          onClick={() =>
            update("calcScriptBindings", [
              ...(section.calcScriptBindings ?? []),
              {
                script: "",
                section: "",
                input_params: [],
                output_table: "",
                trigger: "auto",
              },
            ])
          }
        />
      </CollapsibleCard>

      {/* 📏 Sub-Section Profile */}
      <CollapsibleCard
        icon={Ruler}
        label="章节剖面"
        color="text-cyan-500"
        count={section.subSectionProfile ? 1 : 0}
        open={openMap.profile ?? false}
        onToggle={() => toggle("profile")}
      >
        {section.subSectionProfile && (
          <div className="flex items-center gap-2 px-1">
            <label className="text-muted-foreground text-xs">H2:</label>
            <Input
              type="number"
              value={section.subSectionProfile.expected_h2_count}
              className="h-7 w-16 text-xs"
              onChange={(e) =>
                onChange({
                  subSectionProfile: {
                    ...section.subSectionProfile!,
                    expected_h2_count: +e.target.value,
                  },
                })
              }
            />
            <label className="text-muted-foreground text-xs">H3:</label>
            <Input
              type="number"
              value={section.subSectionProfile.expected_h3_count}
              className="h-7 w-16 text-xs"
              onChange={(e) =>
                onChange({
                  subSectionProfile: {
                    ...section.subSectionProfile!,
                    expected_h3_count: +e.target.value,
                  },
                })
              }
            />
            <label className="text-muted-foreground text-xs">篇幅:</label>
            <select
              className="h-7 rounded border bg-transparent px-1 text-xs"
              value={section.subSectionProfile.volume_estimate}
              onChange={(e) =>
                onChange({
                  subSectionProfile: {
                    ...section.subSectionProfile!,
                    volume_estimate: e.target.value,
                  },
                })
              }
            >
              <option value="short">短</option>
              <option value="medium">中</option>
              <option value="long">长</option>
            </select>
          </div>
        )}
        {!section.subSectionProfile && (
          <AddButton
            label="添加章节剖面"
            onClick={() =>
              onChange({
                subSectionProfile: {
                  expected_h2_count: 0,
                  expected_h3_count: 0,
                  volume_estimate: "medium",
                  notes: "",
                },
              })
            }
          />
        )}
      </CollapsibleCard>
    </div>
  );
}

// ── Helpers ──

function editItem(
  section: EditorSection,
  field:
    | "tableSchemas"
    | "figureRequirements"
    | "formulaReferences"
    | "calcScriptBindings",
  index: number,
  patch: Record<string, unknown>,
  onChange: (u: Partial<EditorSection>) => void,
) {
  const arr = [...(section[field] ?? [])] as unknown as Record<
    string,
    unknown
  >[];
  arr[index] = { ...arr[index], ...patch };
  onChange({ [field]: arr } as Partial<EditorSection>);
}

function CollapsibleCard({
  icon: Icon,
  label,
  color,
  count,
  open,
  onToggle,
  children,
}: {
  icon: React.ElementType;
  label: string;
  color: string;
  count: number;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border-border overflow-hidden rounded-lg border">
      <button
        onClick={onToggle}
        className="hover:bg-accent flex w-full items-center gap-2 px-3 py-2 text-sm"
      >
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        <Icon className={cn("h-4 w-4", color)} />
        <span className="font-medium">{label}</span>
        {count > 0 && (
          <span className="bg-secondary ml-auto rounded-full px-1.5 py-0.5 text-xs">
            {count}
          </span>
        )}
      </button>
      {open && (
        <div className="border-border space-y-1 border-t p-2">{children}</div>
      )}
    </div>
  );
}

function ItemRow({
  children,
  onDelete,
}: {
  children: React.ReactNode;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {children}
      <Button
        variant="ghost"
        size="icon"
        className="text-muted-foreground hover:text-destructive h-7 w-7 shrink-0"
        onClick={onDelete}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

function AddButton({
  onClick,
  label = "添加",
}: {
  onClick: () => void;
  label?: string;
}) {
  return (
    <Button
      variant="outline"
      size="sm"
      className="mt-1 h-7 w-full text-xs"
      onClick={onClick}
    >
      <Plus className="mr-1 h-3.5 w-3.5" /> {label}
    </Button>
  );
}
