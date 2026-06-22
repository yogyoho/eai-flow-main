"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export interface TableSelectOption {
  value: string;
  label: string;
  /** 强调色时显示的色块（可选） */
  swatch?: string;
}

interface TableSelectProps {
  value: string;
  options: TableSelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

/**
 * 表格内紧凑型下拉选择 —— 基于 Shadcn Select。
 * size="sm"，移除阴影，适合嵌入表格单元格。
 */
export function TableSelect({
  value,
  options,
  onChange,
  disabled,
  placeholder,
  className,
}: TableSelectProps) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger
        size="sm"
        className={cn(
          "h-8 min-w-[96px] w-full gap-1.5 px-2.5 shadow-none bg-muted/40 border-transparent hover:bg-muted focus-visible:bg-background",
          className,
        )}
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent position="popper" align="start" className="min-w-[8rem]">
        {options.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            <span className="flex items-center gap-2">
              {opt.swatch && (
                <span
                  className={cn("inline-block size-2.5 rounded-full", opt.swatch)}
                />
              )}
              {opt.label}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
