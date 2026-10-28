import type { FormDefinition, FormField, FormLayout, FormSchema } from "./types";
import { parseJson } from "./utils";

export const FORM_FIELD_TYPES: { value: NonNullable<FormField["type"]>; label: string }[] = [
  { value: "text", label: "单行文本" },
  { value: "textarea", label: "多行文本" },
  { value: "number", label: "数字" },
  { value: "select", label: "下拉选择" },
  { value: "date", label: "日期" },
  { value: "switch", label: "开关" },
];

export const EMPTY_SCHEMA: FormSchema = { fields: [] };

export function formColumns(schema?: FormSchema | null): 1 | 2 {
  return schema?.layout?.columns === 1 ? 1 : 2;
}

export function formFieldSpan(field: FormField, columns: 1 | 2): 1 | 2 {
  if (columns === 1) return 1;
  if (field.span === 1) return 1;
  if (field.span === 2) return 2;
  return field.type === "textarea" ? 2 : 1;
}

export function parseFormSchema(content?: string | null): FormSchema {
  const parsed = parseJson<FormSchema>(content, EMPTY_SCHEMA);
  const fields = Array.isArray(parsed?.fields) ? parsed.fields : [];
  return {
    layout: { columns: parsed?.layout?.columns === 1 ? 1 : 2 },
    fields: fields
      .filter((field) => field && typeof field === "object")
      .map((field) => ({
        ...field,
        key: String(field.key || ""),
        label: String(field.label || field.key || ""),
        type: field.type || "text",
        options: Array.isArray(field.options) ? field.options : [],
        ...(field.span === 1 || field.span === 2 ? { span: field.span } : {}),
      })),
  };
}

export function serializeFormSchema(fields: FormField[], layout?: FormLayout): string {
  return JSON.stringify({
    layout: { columns: layout?.columns === 1 ? 1 : 2 },
    fields: fields.map((field) => ({
      key: field.key,
      label: field.label,
      type: field.type || "text",
      required: Boolean(field.required),
      ...(field.span === 1 || field.span === 2 ? { span: field.span } : {}),
      ...(field.placeholder ? { placeholder: field.placeholder } : {}),
      ...(field.type === "select" ? { options: (field.options || []).filter(Boolean) } : {}),
    })),
  });
}

export function fieldCount(form?: FormDefinition | null): number {
  if (!form?.form_content) return 0;
  return parseFormSchema(form.form_content).fields.length;
}

export function findFormByPath(
  forms: FormDefinition[] | undefined,
  formPath?: string | null,
): FormDefinition | null {
  if (!formPath) return null;
  const list = forms || [];
  const exact = list.find((form) => form.form_path === formPath);
  if (exact) return exact;
  const code = formPath.split(":")[0];
  return list.find((form) => form.form_code === code) || null;
}

export function formValuesFromVariables(variable?: Record<string, unknown> | null): Record<string, unknown> {
  if (!variable) return {};
  const nested = variable.formData;
  const values: Record<string, unknown> = { ...variable };
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    Object.assign(values, nested as Record<string, unknown>);
  }
  delete values.formData;
  return values;
}

/**
 * Fill values that the UI would otherwise show without them being present in
 * state — notably the first option of a select. The browser renders the first
 * option even when the bound value is empty, so required checks must see it.
 * Existing values are always preserved.
 */
export function initialFormValues(
  schema: FormSchema | null | undefined,
  current?: Record<string, unknown> | null,
): Record<string, unknown> {
  const values: Record<string, unknown> = { ...(current || {}) };
  if (!schema?.fields?.length) return values;
  for (const field of schema.fields) {
    if (!field.key) continue;
    const existing = values[field.key];
    if (existing !== undefined && existing !== null && existing !== "") continue;
    if (field.type === "select") {
      if (field.options?.length) values[field.key] = field.options[0];
    } else if (field.type === "switch") {
      values[field.key] = false;
    } else if (existing === undefined) {
      values[field.key] = "";
    }
  }
  return values;
}

export function missingRequiredFields(
  schema: FormSchema | null | undefined,
  values: Record<string, unknown>,
): string[] {
  if (!schema?.fields?.length) return [];
  return schema.fields
    .filter((field) => {
      if (!field.required || !field.key) return false;
      const value = values[field.key];
      return value === undefined || value === null || value === "";
    })
    .map((field) => field.label || field.key);
}
