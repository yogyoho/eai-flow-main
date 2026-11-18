"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface EnumCellSelectProps {
  values: string[];
  value: string;
  onChange: (value: string) => void;
}

/** enum_cell 的响应策略下拉；与全站一致使用 shadcn Select。 */
export function EnumCellSelect({
  values,
  value,
  onChange,
}: EnumCellSelectProps) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        size="sm"
        className="bwe-enum-select"
        aria-label="响应策略"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent
        className="bw-select-menu"
        position="popper"
        align="start"
        sideOffset={4}
      >
        {values.map((item) => (
          <SelectItem key={item} value={item}>
            {item}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
