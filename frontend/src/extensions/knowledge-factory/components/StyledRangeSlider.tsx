"use client";

import type { ChangeEvent, CSSProperties, ReactNode } from "react";

import { cn } from "../utils";

import styles from "./StyledRangeSlider.module.css";

export interface StyledRangeSliderProps {
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  /** 滑块下方说明（如 H1 / H6） */
  footer?: ReactNode;
  className?: string;
  disabled?: boolean;
}

export function StyledRangeSlider({
  min,
  max,
  step,
  value,
  onChange,
  footer,
  className,
  disabled,
}: StyledRangeSliderProps) {
  const span = max - min;
  const pct = span <= 0 ? 0 : ((value - min) / span) * 100;

  return (
    <div className={cn("space-y-2", className)}>
      <div className="rounded-xl bg-zinc-50/80 px-1 py-2 ring-1 ring-zinc-200/80">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={onChange}
          disabled={disabled}
          className={styles.slider}
          style={{ "--slider-pct": `${pct}%` } as CSSProperties}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={value}
        />
      </div>
      {footer}
    </div>
  );
}
