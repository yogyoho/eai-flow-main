"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface StyledCheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  className?: string;
  disabled?: boolean;
}

export function StyledCheckbox({
  checked,
  onChange,
  label,
  className,
  disabled,
}: StyledCheckboxProps) {
  return (
    <label
      className={cn(
        "group flex cursor-pointer items-center gap-2 select-none",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
    >
      <div className="relative">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          className="sr-only"
        />
        <div
          className={cn(
            "flex h-4 w-4 items-center justify-center rounded border-2 transition-all",
            checked
              ? "bg-primary border-primary"
              : "border-muted-foreground/30 bg-background group-hover:border-primary/50",
          )}
        >
          {checked && (
            <Check
              className="text-primary-foreground h-3 w-3"
              strokeWidth={3}
            />
          )}
        </div>
      </div>
      {label && <span className="text-foreground text-xs">{label}</span>}
    </label>
  );
}
