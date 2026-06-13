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

export function StyledCheckbox({ checked, onChange, label, className, disabled }: StyledCheckboxProps) {
  return (
    <label className={cn("flex items-center gap-2 cursor-pointer select-none group", disabled && "opacity-50 cursor-not-allowed", className)}>
      <div className="relative">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          className="sr-only"
        />
        <div className={cn(
          "w-4 h-4 rounded border-2 flex items-center justify-center transition-all",
          checked
            ? "bg-primary border-primary"
            : "border-muted-foreground/30 bg-background group-hover:border-primary/50",
        )}>
          {checked && <Check className="w-3 h-3 text-primary-foreground" strokeWidth={3} />}
        </div>
      </div>
      {label && <span className="text-xs text-foreground">{label}</span>}
    </label>
  );
}
