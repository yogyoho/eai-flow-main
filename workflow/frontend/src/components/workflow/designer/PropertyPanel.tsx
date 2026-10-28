"use client";

import { useState } from "react";
import {
  CircleDot,
  CirclePlay,
  Diamond,
  GitBranch,
  Plus,
  Settings2,
  Split,
  SquareStack,
  Trash2,
  UserPlus,
  X,
} from "lucide-react";
import type {
  FormDefinition,
  HandlerOption,
  NodeTypeName,
} from "@/lib/types";
import type { DefinitionMeta } from "./graph";
import { NODE_TYPE_META } from "./nodeRegistry";
import { HandlerPicker, handlerNames } from "./HandlerPicker";
import { FormPicker } from "./FormPicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export type DesignerSelection =
  | {
      kind: "node";
      id: string;
      type: NodeTypeName;
      text: string;
      properties: Record<string, unknown>;
    }
  | {
      kind: "edge";
      id: string;
      text: string;
      source: string;
      target: string;
      properties: Record<string, unknown>;
    };

const TYPE_ICON: Record<
  NodeTypeName,
  React.ComponentType<{ className?: string; style?: React.CSSProperties }>
> = {
  start: CirclePlay,
  between: SquareStack,
  end: CircleDot,
  serial: Split,
  parallel: GitBranch,
  inclusive: Diamond,
};

const LISTENERS = [
  { value: "", label: "不配置" },
  { value: "http", label: "HTTP Webhook" },
  { value: "mq", label: "消息队列" },
  { value: "script", label: "安全脚本" },
];

export function PropertyPanel({
  flow,
  selection,
  forms,
  handlers,
  nextOptions,
  onChangeFlow,
  onChangeNode,
  onChangeEdge,
  onDelete,
}: {
  flow: DefinitionMeta;
  selection: DesignerSelection | null;
  forms: FormDefinition[];
  handlers: HandlerOption[];
  nextOptions: { code: string; label: string }[];
  onChangeFlow: (patch: Partial<DefinitionMeta>) => void;
  onChangeNode: (
    id: string,
    updates: { text?: string; properties?: Record<string, unknown> },
  ) => void;
  onChangeEdge: (
    id: string,
    updates: { text?: string; properties?: Record<string, unknown> },
  ) => void;
  onDelete: () => void;
}) {
  return (
    <aside className="flex w-[330px] shrink-0 flex-col border-l border-border bg-card">
      {selection?.kind === "node" ? (
        <NodePanel
          key={selection.id}
          selection={selection}
          forms={forms}
          handlers={handlers}
          nextOptions={nextOptions}
          onChange={onChangeNode}
          onDelete={onDelete}
        />
      ) : selection?.kind === "edge" ? (
        <EdgePanel
          key={selection.id}
          selection={selection}
          onChange={onChangeEdge}
          onDelete={onDelete}
        />
      ) : (
        <FlowPanel
          flow={flow}
          forms={forms}
          onChange={onChangeFlow}
        />
      )}
    </aside>
  );
}

function PanelHeader({
  icon,
  title,
  subtitle,
  onDelete,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  onDelete?: () => void;
}) {
  return (
    <div className="flex items-start gap-3 border-b border-border px-4 py-4">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold">{title}</p>
        <p className="truncate text-[10.5px] text-muted-foreground">{subtitle}</p>
      </div>
      {onDelete && (
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-muted-foreground hover:text-destructive"
          onClick={onDelete}
          title="删除"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <label className="text-[11.5px] font-medium text-foreground">{label}</label>
      {children}
      {hint && <p className="text-[10.5px] leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  );
}

function NodePanel({
  selection,
  forms,
  handlers,
  nextOptions,
  onChange,
  onDelete,
}: {
  selection: Extract<DesignerSelection, { kind: "node" }>;
  forms: FormDefinition[];
  handlers: HandlerOption[];
  nextOptions: { code: string; label: string }[];
  onChange: (
    id: string,
    updates: { text?: string; properties?: Record<string, unknown> },
  ) => void;
  onDelete: () => void;
}) {
  const [handlerOpen, setHandlerOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const meta = NODE_TYPE_META[selection.type];
  const Icon = TYPE_ICON[selection.type];
  const properties = selection.properties;
  const permissionFlag = String(properties.permissionFlag || "");
  const formCustom = String(properties.formCustom || "N") === "Y";
  const extMap = (properties.extMap as Record<string, unknown>) || {};
  const names = handlerNames(permissionFlag, handlers);

  function patch(values: Record<string, unknown>) {
    onChange(selection.id, { properties: values });
  }

  const selectedForm = forms.find(
    (form) =>
      (form.form_path || `${form.form_code}:${form.version}`) === String(properties.formPath || ""),
  );

  return (
    <>
      <PanelHeader
        icon={<Icon className="h-4 w-4" style={{ color: meta.color }} />}
        title={meta.label}
        subtitle={selection.id}
        onDelete={onDelete}
      />
      <div className="flex-1 overflow-y-auto">
        <div className="panel-section space-y-4">
          <div className="panel-label">基础信息</div>
          <Field label="节点名称">
            <Input
              value={selection.text}
              onChange={(event) => onChange(selection.id, { text: event.target.value })}
              placeholder={meta.short}
            />
          </Field>
          <Field label="节点编码" hint="保存后作为运行时的节点唯一标识">
            <Input value={selection.id} disabled className="font-mono text-[12px]" />
          </Field>
          {selection.type === "between" && (
            <Field label="节点类型">
              <div className="flex h-9 items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 text-[12px] text-muted-foreground">
                人工审批 · 单人 / 会签
              </div>
            </Field>
          )}
        </div>

        {selection.type === "between" && (
          <div className="panel-section space-y-4">
            <div className="panel-label">办理人</div>
            <div className="flex flex-wrap gap-1.5">
              {names.length === 0 ? (
                <span className="text-[11px] text-muted-foreground">
                  未指定，运行时默认回退给发起人
                </span>
              ) : (
                names.map((name) => (
                  <span
                    key={name}
                    className="inline-flex items-center gap-1 rounded-full border border-primary/15 bg-primary/5 px-2 py-0.5 text-[11px] text-primary"
                  >
                    {name}
                  </span>
                ))
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="w-full border-dashed"
              onClick={() => setHandlerOpen(true)}
            >
              <UserPlus className="h-3.5 w-3.5" />
              选择用户 / 角色 / 部门
            </Button>
            <Field
              label="会签比例"
              hint="0 为单人办理；1–99 为通过百分比；100 为会签全员通过。追加 @@sequence 表示顺序会签。"
            >
              <Input
                value={String(properties.nodeRatio || "0")}
                onChange={(event) => patch({ nodeRatio: event.target.value })}
                placeholder="0"
                className="font-mono text-[12px]"
              />
            </Field>
            <div className="flex flex-wrap gap-1.5">
              {["0", "50", "100", "100@@sequence"].map((ratio) => (
                <button
                  key={ratio}
                  type="button"
                  onClick={() => patch({ nodeRatio: ratio })}
                  className={cn(
                    "rounded-md border px-2 py-1 text-[10.5px] transition",
                    String(properties.nodeRatio || "0") === ratio
                      ? "border-primary/40 bg-primary/5 text-primary"
                      : "border-border text-muted-foreground hover:border-foreground/25",
                  )}
                >
                  {ratio === "0" ? "单人" : ratio === "100" ? "会签 100%" : ratio}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="panel-section space-y-4">
          <div className="panel-label">表单与规则</div>
          <Field label="自定义表单">
            <div className="flex rounded-lg border border-border bg-muted/30 p-0.5">
              {[
                { value: "N", label: "不使用" },
                { value: "Y", label: "自定义表单" },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() =>
                    patch({
                      formCustom: item.value,
                      formPath: item.value === "N" ? "" : properties.formPath,
                    })
                  }
                  className={cn(
                    "flex-1 rounded-md py-1.5 text-[11.5px] transition",
                    (formCustom ? "Y" : "N") === item.value
                      ? "bg-card font-medium text-primary shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </Field>
          {formCustom && (
            <Field label="业务表单">
              <button
                type="button"
                onClick={() => setFormOpen(true)}
                className="flex h-9 w-full items-center justify-between rounded-lg border border-input bg-card px-3 text-left text-[12px] transition hover:border-foreground/25"
              >
                <span className={cn("truncate", !selectedForm && "text-muted-foreground/70")}>
                  {selectedForm ? selectedForm.form_name : String(properties.formPath || "选择表单…")}
                </span>
                <Settings2 className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            </Field>
          )}
          <Field label="自动跳过" hint="满足条件时无需人工审批，直接跳到目标节点">
            <Select
              value={String(properties.anyNodeSkip || "")}
              onValueChange={(value) => patch({ anyNodeSkip: value })}
              placeholder="不自动跳过"
              options={[
                { value: "", label: "不自动跳过" },
                ...nextOptions.map((option) => ({
                  value: option.code,
                  label: option.label,
                })),
              ]}
            />
          </Field>
          <Field label="监听器类型">
            <Select
              value={String(properties.listenerType || "")}
              onValueChange={(value) => patch({ listenerType: value })}
              options={LISTENERS.map((listener) => ({
                value: listener.value,
                label: listener.label,
              }))}
            />
          </Field>
          {properties.listenerType ? (
            <Field label="监听器地址">
              <Input
                value={String(properties.listenerPath || "")}
                onChange={(event) => patch({ listenerPath: event.target.value })}
                placeholder="https://example.com/hooks/flow"
              />
            </Field>
          ) : null}
        </div>

        <div className="panel-section space-y-3">
          <div className="flex items-center justify-between">
            <div className="panel-label">扩展属性</div>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => patch({ extMap: { ...extMap, "": "" } })}
            >
              <Plus className="h-3 w-3" />
              添加
            </Button>
          </div>
          {Object.keys(extMap).length === 0 && (
            <p className="text-[10.5px] text-muted-foreground">
              可配置审批类型、超时小时、通知渠道等业务扩展字段。
            </p>
          )}
          {Object.entries(extMap).map(([key, value]) => (
            <div key={key} className="flex items-start gap-1.5">
              <Input
                value={key}
                onChange={(event) => {
                  const next: Record<string, unknown> = {};
                  for (const [k, v] of Object.entries(extMap)) {
                    next[k === key ? event.target.value : k] = v;
                  }
                  patch({ extMap: next });
                }}
                placeholder="code"
                className="h-8 w-[38%] font-mono text-[11px]"
              />
              <Input
                value={String(value ?? "")}
                onChange={(event) => patch({ extMap: { ...extMap, [key]: event.target.value } })}
                placeholder="value"
                className="h-8 flex-1 text-[11px]"
              />
              <Button
                variant="ghost"
                size="icon-sm"
                className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => {
                  const next = { ...extMap };
                  delete next[key];
                  patch({ extMap: next });
                }}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>

      </div>

      <HandlerPicker
        open={handlerOpen}
        value={permissionFlag}
        onOpenChange={setHandlerOpen}
        onConfirm={(value) => patch({ permissionFlag: value })}
      />
      <FormPicker
        open={formOpen}
        forms={forms}
        value={String(properties.formPath || "")}
        onOpenChange={setFormOpen}
        onConfirm={(value) => patch({ formPath: value || "" })}
      />
    </>
  );
}

function EdgePanel({
  selection,
  onChange,
  onDelete,
}: {
  selection: Extract<DesignerSelection, { kind: "edge" }>;
  onChange: (
    id: string,
    updates: { text?: string; properties?: Record<string, unknown> },
  ) => void;
  onDelete: () => void;
}) {
  const properties = selection.properties;
  const skipType = String(properties.skipType || "PASS");
  const condition = String(properties.skipCondition || "");

  function patch(values: Record<string, unknown>) {
    onChange(selection.id, { properties: values });
  }

  return (
    <>
      <PanelHeader
        icon={<GitBranch className="h-4 w-4 text-primary" />}
        title="跳转连线"
        subtitle={`${selection.source} → ${selection.target}`}
        onDelete={onDelete}
      />
      <div className="flex-1 overflow-y-auto">
        <div className="panel-section space-y-4">
          <div className="panel-label">基础信息</div>
          <Field label="跳转名称">
            <Input
              value={selection.text}
              onChange={(event) => onChange(selection.id, { text: event.target.value })}
              placeholder="通过 / 退回 / 金额 ≥ 5000"
            />
          </Field>
          <Field label="跳转类型">
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { value: "PASS", label: "通过", tone: "text-emerald-700 border-emerald-200 bg-emerald-50" },
                { value: "REJECT", label: "退回", tone: "text-rose-700 border-rose-200 bg-rose-50" },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => patch({ skipType: item.value })}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-[12px] transition",
                    skipType === item.value
                      ? item.tone
                      : "border-border text-muted-foreground hover:border-foreground/20",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </Field>
          <div className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2 text-[11px]">
            <span className="text-muted-foreground">目标节点</span>
            <span className="font-mono text-foreground">{selection.target}</span>
          </div>
        </div>

        {skipType === "PASS" && (
          <div className="panel-section space-y-4">
            <div className="panel-label">跳转条件</div>
            <Field
              label="条件表达式"
              hint="格式：操作符@@变量|值。为空表示无条件通过；default@@ 作为兜底分支。"
            >
              <Textarea
                value={condition}
                onChange={(event) => patch({ skipCondition: event.target.value })}
                placeholder="le@@amount|5000"
                className="h-[76px] font-mono text-[12px]"
              />
            </Field>
            <div className="flex flex-wrap gap-1.5">
              {["le@@amount|5000", "gt@@amount|5000", "eq@@type|A", "default@@"].map((expr) => (
                <button
                  key={expr}
                  type="button"
                  onClick={() => patch({ skipCondition: expr })}
                  className="rounded-md border border-border bg-card px-2 py-1 font-mono text-[10px] text-muted-foreground transition hover:border-primary/40 hover:text-primary"
                >
                  {expr}
                </button>
              ))}
            </div>
            <div className="rounded-lg border border-sky-100 bg-sky-50/70 p-3 text-[10.5px] leading-relaxed text-sky-800">
              支持的操作符：eq / ne / gt / ge / lt / le / like / notLike。SpEL 子集使用{" "}
              <code>spel@@</code> 前缀，服务端以安全 AST 求值，禁止任意代码执行。
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function FlowPanel({
  flow,
  forms,
  onChange,
}: {
  flow: DefinitionMeta;
  forms: FormDefinition[];
  onChange: (patch: Partial<DefinitionMeta>) => void;
}) {
  const [formOpen, setFormOpen] = useState(false);
  const formCustom = (flow.formCustom || "N") === "Y";
  const selectedForm = forms.find(
    (form) => (form.form_path || `${form.form_code}:${form.version}`) === (flow.formPath || ""),
  );

  return (
    <>
      <PanelHeader
        icon={<Settings2 className="h-4 w-4 text-primary" />}
        title="流程属性"
        subtitle="未选择画布元素"
      />
      <div className="flex-1 overflow-y-auto">
        <div className="panel-section space-y-4">
          <div className="panel-label">基础信息</div>
          <Field label="流程名称">
            <Input
              value={flow.flowName}
              onChange={(event) => onChange({ flowName: event.target.value })}
            />
          </Field>
          <Field label="流程编码" hint="编码创建后不可修改；复制版本会沿用同一编码">
            <Input
              value={flow.flowCode}
              disabled={Boolean(flow.id)}
              onChange={(event) => onChange({ flowCode: event.target.value })}
              className="font-mono text-[12px]"
              placeholder="例如 leave / expense"
            />
          </Field>
          <Field label="分类">
            <Input
              value={flow.category || ""}
              onChange={(event) => onChange({ category: event.target.value })}
              placeholder="人事 / 财务 / 采购"
            />
          </Field>
        </div>

        <div className="panel-section space-y-4">
          <div className="panel-label">流程表单</div>
          <Field label="自定义表单">
            <div className="flex rounded-lg border border-border bg-muted/30 p-0.5">
              {[
                { value: "N", label: "不使用" },
                { value: "Y", label: "自定义表单" },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() =>
                    onChange({ formCustom: item.value, formPath: item.value === "N" ? null : flow.formPath })
                  }
                  className={cn(
                    "flex-1 rounded-md py-1.5 text-[11.5px] transition",
                    (formCustom ? "Y" : "N") === item.value
                      ? "bg-card font-medium text-primary shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </Field>
          {formCustom && (
            <Field label="业务表单">
              <button
                type="button"
                onClick={() => setFormOpen(true)}
                className="flex h-9 w-full items-center justify-between rounded-lg border border-input bg-card px-3 text-left text-[12px] transition hover:border-foreground/25"
              >
                <span className={cn("truncate", !selectedForm && "text-muted-foreground/70")}>
                  {selectedForm ? selectedForm.form_name : flow.formPath || "选择表单…"}
                </span>
                <Settings2 className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            </Field>
          )}
        </div>

        <div className="panel-section space-y-4">
          <div className="panel-label">监听器</div>
          <Field label="监听器类型">
            <Select
              value={flow.listenerType || ""}
              onValueChange={(value) => onChange({ listenerType: value })}
              options={LISTENERS.map((listener) => ({
                value: listener.value,
                label: listener.label,
              }))}
            />
          </Field>
          {flow.listenerType ? (
            <Field label="监听器地址">
              <Input
                value={flow.listenerPath || ""}
                onChange={(event) => onChange({ listenerPath: event.target.value })}
                placeholder="https://example.com/hooks/flow"
              />
            </Field>
          ) : null}
        </div>

        <div className="panel-section space-y-2">
          <div className="panel-label">版本信息</div>
          <InfoRow label="当前版本" value={flow.version ? `v${flow.version}` : "未保存"} />
          <InfoRow
            label="发布状态"
            value={flow.isPublish === 1 ? "已发布" : flow.isPublish === 9 ? "已失效" : "未发布"}
          />
          <InfoRow label="流程 ID" value={flow.id ? String(flow.id) : "新建"} />
        </div>
      </div>

      <FormPicker
        open={formOpen}
        forms={forms}
        value={flow.formPath || ""}
        onOpenChange={setFormOpen}
        onConfirm={(value) => onChange({ formPath: value })}
      />
    </>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1 text-[11px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-foreground">{value}</span>
    </div>
  );
}
