/**
 * cn() — 从主系统 frontend/src/lib/utils.ts 提取（S2 Task 1）。
 * 复制的 ontology / bid-quote 组件均依赖此签名，保持一致以便未来回同步。
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
