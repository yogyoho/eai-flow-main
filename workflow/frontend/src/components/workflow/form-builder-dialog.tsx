"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  Eye,
  FileText,
  GripVertical,
  Loader2,
  Plus,
  Save,
  Trash2,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { FormDefinition, FormField, FormSchema } from "@/lib/types";
import {
  FORM_FIELD_TYPES,
  formFieldSpan,
  parseFormSchema,
  serializeFormSchema,
} from "@/lib/forms";
import { cn, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FormRenderer } from "@/components/workflow/form-renderer";

function newField(index: number): FormField {
  return {
    key: `field_${index + 1}`,
    label: `字段 ${index + 1}`,
    type: "text",
    required: false,
  };
}

export function FormBuilderDialog({
  open,
  onOpenChange,
  form,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  form: FormDefinition | null;
  onSaved?: (form: FormDefinition) => void;
}) {
  const queryClient = useQueryClient();
  const editing = Boolean(form);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [fields, setFields] = useState<FormField[]>([]);
  const [columns, setColumns] = useState<1 | 2>(2);
  const [values, setValues] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (!open) return;
    if (form) {
      const parsed = parseFormSchema(form.form_content);
      setName(form.form_name);
      setCode(form.form_code);
      setFields(parsed.fields);
      setColumns(parsed.layout?.columns === 1 ? 1 : 2);
    } else {
      setName("");
      setCode(`form_${Math.random().toString(36).slice(2, 8)}`);
      setFields([newField(0)]);
      setColumns(2);
    }
    setValues({});
  }, [open, form]);

  const schema = useMemo<FormSchema>(
    () => ({ layout: { columns }, fields }),
    [columns, fields],
  );
  const fieldCount = fields.filter((field) => field.key.trim()).length;

  function patchField(index: number, patch: Partial<FormField>) {
    setFields((current) =>
      current.map((field, position) => (position === index ? { ...field, ...patch } : field)),
    );
  }

  function moveField(index: number, delta: number) {
    setFields((current) => {
      const next = [...current];
      const target = index + delta;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  const mutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) throw new ApiError("请填写表单名称", 400);
      if (!code.trim()) throw new ApiError("请填写表单编码", 400);
      const keys = fields.map((field) => field.key.trim()).filter(Boolean);
      if (!keys.length) throw new ApiError("至少添加一个字段", 400);
      if (keys.length !== fields.length) throw new ApiError("字段 key 不能为空", 400);
      if (new Set(keys).size !== keys.length) throw new ApiError("字段 key 不能重复", 400);
      const payload = {
        form_name: name.trim(),
        form_content: serializeFormSchema(fields, { columns }),
        form_type: 0,
      };
      if (form) return api.forms.update(form.id, payload);
      return api.forms.create({ ...payload, form_code: code.trim() });
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["forms"] });
      queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
      toast.success(editing ? "表单已更新" : "表单已创建");
      onOpenChange(false);
      onSaved?.(saved);
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "保存失败"),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100vh-2rem)] max-w-[1280px] overflow-y-auto p-0">
        <DialogHeader className="border-b border-border px-6 py-4">
          <DialogTitle className="flex items-center gap-2 text-[16px]">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-4 w-4" />
            </span>
            {editing ? "编辑业务表单" : "新建业务表单"}
          </DialogTitle>
          <DialogDescription>
            字段 schema 以 JSON 保存在 flow_form.form_content，流程节点通过 form_path 引用。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_440px]">
          <div className="space-y-5 p-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="form-name">
                  表单名称 <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="form-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="例如：费用报销单"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="form-code">
                  表单编码 <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="form-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  disabled={editing}
                  placeholder="expense_form"
                  className="font-mono text-[13px] disabled:bg-muted/40"
                />
                <p className="text-[10.5px] text-muted-foreground">
                  编码用于 form_path 引用，创建后不可修改。
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[12.5px] font-semibold">字段设计</p>
                <p className="text-[10.5px] text-muted-foreground">
                  共 {fieldCount} 个字段 · {columns === 1 ? "单列" : "双列"}布局 · 字段 key 会作为流程变量名
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-muted-foreground">表单布局</span>
                  <div className="inline-flex rounded-lg border border-border bg-card p-0.5">
                    {([1, 2] as const).map((value) => (
                      <button
                        key={value}
                        type="button"
                        aria-pressed={columns === value}
                        onClick={() => setColumns(value)}
                        className={cn(
                          "rounded-md px-2.5 py-1 text-[11px] font-medium transition",
                          columns === value
                            ? "bg-primary text-primary-foreground shadow-sm"
                            : "text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {value === 1 ? "单列" : "双列"}
                      </button>
                    ))}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setFields((current) => [...current, newField(current.length)])}
                >
                  <Plus className="h-3.5 w-3.5" />
                  添加字段
                </Button>
              </div>
            </div>

            {fields.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-10 text-center">
                <Wand2 className="mx-auto h-6 w-6 text-muted-foreground/60" />
                <p className="mt-2 text-[12.5px] font-medium">还没有字段</p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  添加字段后可在右侧实时预览表单效果。
                </p>
                <Button
                  size="sm"
                  className="mt-3"
                  onClick={() => setFields([newField(0)])}
                >
                  <Plus className="h-3.5 w-3.5" />
                  添加第一个字段
                </Button>
              </div>
            ) : (
              <div className="space-y-2.5">
                {fields.map((field, index) => {
                  const span = formFieldSpan(field, columns);
                  return (
                  <div
                    key={index}
                    className="rounded-xl border border-border bg-card p-3 transition hover:border-foreground/15"
                  >
                    <div className="flex items-center gap-2">
                      <GripVertical className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                      <span className="flex h-5 min-w-5 items-center justify-center rounded bg-muted text-[10px] font-medium text-muted-foreground">
                        {index + 1}
                      </span>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {field.type || "text"}
                      </Badge>
                      <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
                        {columns === 1 || span === 2 ? "整行" : "半宽"}
                      </Badge>
                      <div className="ml-auto flex items-center gap-0.5">
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          title="上移"
                          disabled={index === 0}
                          onClick={() => moveField(index, -1)}
                        >
                          <ArrowUp className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          title="下移"
                          disabled={index === fields.length - 1}
                          onClick={() => moveField(index, 1)}
                        >
                          <ArrowDown className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          title="删除字段"
                          className="text-muted-foreground hover:text-destructive"
                          onClick={() =>
                            setFields((current) =>
                              current.filter((_, position) => position !== index),
                            )
                          }
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>

                    <div className="mt-2.5 grid gap-2 sm:grid-cols-[minmax(0,1fr)_180px]">
                      <Input
                        value={field.label || ""}
                        onChange={(event) => patchField(index, { label: event.target.value })}
                        placeholder="字段标签"
                        className="h-8 text-[12px]"
                      />
                      <Input
                        value={field.key || ""}
                        onChange={(event) => patchField(index, { key: event.target.value })}
                        placeholder="字段 key"
                        className="h-8 font-mono text-[11.5px]"
                      />
                    </div>

                    <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_140px_auto]">
                      <Select
                        value={field.type || "text"}
                        onValueChange={(value) =>
                          patchField(index, {
                            type: value as FormField["type"],
                          })
                        }
                        options={FORM_FIELD_TYPES.map((type) => ({
                          value: type.value,
                          label: type.label,
                        }))}
                        aria-label="字段类型"
                        className="h-8 text-[12px]"
                      />
                      {columns === 1 ? (
                        <div className="flex h-8 items-center rounded-lg border border-input bg-muted/40 px-3 text-[11.5px] text-muted-foreground">
                          整行（单列）
                        </div>
                      ) : (
                        <Select
                          value={String(span)}
                          onValueChange={(value) =>
                            patchField(index, { span: value === "2" ? 2 : 1 })
                          }
                          options={[
                            { value: "1", label: "半宽（1 列）" },
                            { value: "2", label: "整行（2 列）" },
                          ]}
                          aria-label="字段宽度"
                          className="h-8 text-[12px]"
                        />
                      )}
                      <label className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap text-[11.5px] text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={Boolean(field.required)}
                          onChange={(event) =>
                            patchField(index, { required: event.target.checked })
                          }
                          className="accent-[var(--primary)]"
                        />
                        必填
                      </label>
                    </div>

                    {field.type === "select" && (
                      <div className="mt-2">
                        <Input
                          defaultValue={(field.options || []).join(", ")}
                          onBlur={(event) =>
                            patchField(index, {
                              options: event.target.value
                                .split(",")
                                .map((option) => option.trim())
                                .filter(Boolean),
                            })
                          }
                          placeholder="选项 1, 选项 2, 选项 3"
                          className="h-8 text-[11.5px]"
                        />
                        <p className="mt-1 text-[10px] text-muted-foreground">
                          多个选项用英文逗号分隔，失焦后保存。
                        </p>
                      </div>
                    )}
                  </div>
                  );
                })}
              </div>
            )}
          </div>

          <aside className="border-t border-border bg-muted/20 p-6 lg:border-l lg:border-t-0">
            <div className="flex items-center gap-2">
              <Eye className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-[12px] font-semibold">实时预览</p>
            </div>
            <p className="mt-1 text-[10.5px] text-muted-foreground">
              仅演示填写效果，不会保存预览数据。
            </p>
            <div className="mt-4 rounded-xl border border-border bg-card p-4">
              {fields.some((field) => field.key) ? (
                <FormRenderer
                  schema={schema}
                  values={values}
                  onChange={setValues}
                  compact
                />
              ) : (
                <p className="py-10 text-center text-[11.5px] text-muted-foreground">
                  添加字段后显示预览
                </p>
              )}
            </div>
            {form && (
              <div className="mt-4 rounded-xl border border-border bg-card p-3.5 text-[11px] text-muted-foreground">
                <div className="flex items-center justify-between">
                  <span>版本</span>
                  <span className="font-mono text-foreground">v{form.version}</span>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span>form_path</span>
                  <span className="font-mono text-foreground">{form.form_path || "—"}</span>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span>更新时间</span>
                  <span className="text-foreground">{formatDate(form.update_time)}</span>
                </div>
              </div>
            )}
          </aside>
        </div>

        <DialogFooter className="border-t border-border px-6 py-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
            取消
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {mutation.isPending ? "保存中…" : editing ? "保存修改" : "创建表单"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
