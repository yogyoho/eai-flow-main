"use client";

import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { ChevronDownIcon, CheckIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export interface AdminSelectOption {
  value: string;
  label: string;
}

interface AdminSelectProps {
  value: string;
  onChange?: (value: string) => void;
  onValueChange?: (value: string) => void;
  options: AdminSelectOption[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

function AdminSelect({
  value,
  onChange,
  onValueChange,
  options,
  placeholder = "Select...",
  className,
  disabled = false,
}: AdminSelectProps) {
    return (
      <SelectPrimitive.Root value={value} onValueChange={(v) => { onChange?.(v); onValueChange?.(v); }} disabled={disabled}>
      <SelectPrimitive.Trigger
        className={cn(
          "flex items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm transition-colors",
          "focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring",
          "hover:border-input",
          disabled && "opacity-50 cursor-not-allowed bg-muted",
          className
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder}>
          {options.find((o) => o.value === value)?.label ?? placeholder}
        </SelectPrimitive.Value>
        <SelectPrimitive.Icon>
          <ChevronDownIcon className="h-4 w-4 opacity-50" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className={cn(
            "relative z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
            "data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2",
            "data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2"
          )}
          position="popper"
          sideOffset={4}
        >
          <SelectPrimitive.Viewport
            className="p-1"
            style={{ minWidth: "var(--radix-select-trigger-width)" }}
          >
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className={cn(
                  "relative flex w-full cursor-pointer items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none",
                  "focus:bg-accent focus:text-accent-foreground",
                  "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
                  "data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground"
                )}
              >
                <span className="absolute left-2 flex size-3.5 items-center justify-center">
                  <SelectPrimitive.ItemIndicator>
                    <CheckIcon className="size-4" />
                  </SelectPrimitive.ItemIndicator>
                </span>
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

export { AdminSelect };
