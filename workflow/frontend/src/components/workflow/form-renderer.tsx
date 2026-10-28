"use client";

import type { FormField, FormSchema } from "@/lib/types";
import { formColumns, formFieldSpan } from "@/lib/forms";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { EmptyState } from "@/components/ui/empty-state";
import { cn, coerceValue } from "@/lib/utils";

export function FormRenderer({
  schema,
  values,
  onChange,
  readOnly,
  compact,
}: {
  schema?: FormSchema | null;
  values: Record<string, unknown>;
  onChange?: (values: Record<string, unknown>) => void;
  readOnly?: boolean;
  compact?: boolean;
}) {
  const fields = schema?.fields?.filter((field) => field.key) || [];
  const columns = formColumns(schema);

  if (!fields.length) {
    return (
      <EmptyState
        title="该节点未绑定表单"
        description="审批时只记录意见与流转结果，业务变量仍会随流程实例保存。"
        className="py-10"
      />
    );
  }

  function update(key: string, raw: unknown) {
    if (!onChange) return;
    onChange({ ...values, [key]: raw });
  }

  return (
    <div
      className={cn(
        "grid",
        compact ? "gap-3" : "gap-4",
        columns === 1 ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2",
      )}
    >
      {fields.map((field) => {
        const span = formFieldSpan(field, columns);
        return (
          <FieldRenderer
            key={field.key}
            field={field}
            value={values[field.key]}
            readOnly={readOnly}
            wide={span === 2}
            onChange={(value) => update(field.key, value)}
          />
        );
      })}
    </div>
  );
}

function FieldRenderer({
  field,
  value,
  readOnly,
  wide,
  onChange,
}: {
  field: FormField;
  value: unknown;
  readOnly?: boolean;
  wide?: boolean;
  onChange: (value: unknown) => void;
}) {
  const text = value === undefined || value === null ? "" : String(value);
  const common = `h-9 w-full ${readOnly ? "bg-muted/40 text-muted-foreground" : ""}`;

  return (
    <div className={cn("grid min-w-0 gap-1.5", wide && "sm:col-span-2")}>
      <label className="text-[11.5px] font-medium text-foreground">
        {field.label || field.key}
        {field.required && <span className="ml-0.5 text-destructive">*</span>}
      </label>
      {field.type === "textarea" ? (
        <Textarea
          value={text}
          readOnly={readOnly}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder || `请输入${field.label || ""}`}
          className={readOnly ? "bg-muted/40 text-muted-foreground" : ""}
        />
      ) : field.type === "select" ? (
        <Select
          value={text}
          onValueChange={onChange}
          disabled={readOnly}
          placeholder="请选择…"
          options={(field.options || []).map((option) => ({
            value: option,
            label: option,
          }))}
          className={common}
        />
      ) : field.type === "switch" ? (
        <button
          type="button"
          disabled={readOnly}
          onClick={() => onChange(!(value === true || value === "true"))}
          className={cn(
            "flex h-9 w-full items-center justify-between rounded-lg border border-input bg-card px-3 text-[12px] transition",
            readOnly && "bg-muted/40",
          )}
        >
          <span className="text-muted-foreground">{text === "true" || value === true ? "是" : "否"}</span>
          <span
            className={cn(
              "relative h-5 w-9 rounded-full transition",
              text === "true" || value === true ? "bg-primary" : "bg-slate-300",
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition",
                text === "true" || value === true ? "left-[18px]" : "left-0.5",
              )}
            />
          </span>
        </button>
      ) : (
        <Input
          type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
          value={text}
          readOnly={readOnly}
          onChange={(event) =>
            onChange(field.type === "number" ? coerceValue(event.target.value) : event.target.value)
          }
          placeholder={field.placeholder || `请输入${field.label || ""}`}
          className={common}
        />
      )}
      {field.placeholder && field.type !== "textarea" && (
        <p className="text-[10.5px] text-muted-foreground">{field.placeholder}</p>
      )}
    </div>
  );
}
