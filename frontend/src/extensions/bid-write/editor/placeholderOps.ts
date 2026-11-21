// EAI-CUSTOM——占位符填值通道(写作工作台可用性修复:核心商务数值此前无 UI
// 填写面,唯一文档化路径「③重新生成」又绝不覆盖已有正文=死路)。
// 走 state.ts system 事务(constraints 放行、不入撤销栈)——与审批替换/缺件补录
// 同通道,不破坏 M1 只读不变式。
import type { Node as PMNode } from "prosemirror-model";
import { type EditorState, type Transaction } from "prosemirror-state";

import { systemTr } from "./state";

export interface PlaceholderHit {
  pos: number;
  slotId: string;
  label: string;
  value: string;
  placeholderType: string;
}

/** attrs 值安全字符串化(unknown 直 String() 会被 no-base-to-string 拦)。 */
function attrStr(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** 变量标签归一化:全半角空白全剥——「日  期」「日      期」「日期」同变量。 */
export function normalizeVarLabel(label: string): string {
  return label.replace(/[\s\u3000]+/g, "");
}

interface PlaceholderAttrsLike {
  slot_id: unknown;
  label: unknown;
  value: unknown;
  placeholder_type: unknown;
}

/** 按 slot_id 找占位符(命中全部同槽位原子——slot 派生自 block index,通常唯一)。 */
export function findPlaceholderHits(
  doc: PMNode,
  slotId: string,
): PlaceholderHit[] {
  const hits: PlaceholderHit[] = [];
  doc.descendants((node, pos) => {
    if (node.type.name === "placeholder") {
      const attrs = node.attrs as unknown as PlaceholderAttrsLike;
      const hitSlot = attrStr(attrs.slot_id);
      if (hitSlot === slotId) {
        hits.push({
          pos,
          slotId,
          label: attrStr(attrs.label),
          value: attrStr(attrs.value),
          placeholderType: attrStr(attrs.placeholder_type),
        });
      }
    }
    return true;
  });
  return hits;
}

/**
 * 同变量全集(批卅六-b 全局替换):slot_id 按出现位置派生,签署日期等逻辑变量
 * 会裂成 N 个独立 slot——只填一个 slot 是「改了 1 处漏 N-1 处」的废标隐患。
 * 同变量判定=归一化标签相同 + (当前值相同 或 未填);
 * (类型不参与:underscore/date 都是签署日期,按类型拆变量=又改 1 漏 N-1)
 * 同标签但已填不同值=用户显式改过的特例,不连带(尊重既有差异)。
 */
export function findVariableHits(
  doc: PMNode,
  slotId: string,
): PlaceholderHit[] {
  const ref = findPlaceholderHits(doc, slotId)[0];
  if (!ref) return [];
  const refLabel = normalizeVarLabel(ref.label);
  const hits: PlaceholderHit[] = [];
  doc.descendants((node, pos) => {
    if (node.type.name === "placeholder") {
      const attrs = node.attrs as unknown as PlaceholderAttrsLike;
      const value = attrStr(attrs.value);
      if (
        normalizeVarLabel(attrStr(attrs.label)) === refLabel &&
        (value === ref.value || value === "")
      ) {
        hits.push({
          pos,
          slotId: attrStr(attrs.slot_id),
          label: attrStr(attrs.label),
          value,
          placeholderType: attrStr(attrs.placeholder_type),
        });
      }
    }
    return true;
  });
  return hits;
}

/** 填值=system 事务 setNodeAttribute(value);slot 不存在/值为空白→null 不猜。 */
export function setPlaceholderValue(
  state: EditorState,
  slotId: string,
  value: string,
): Transaction | null {
  const text = value.trim();
  if (!slotId || text === "") return null;
  const hits = findPlaceholderHits(state.doc, slotId);
  if (hits.length === 0) return null;
  const tr = state.tr;
  for (const hit of hits) tr.setNodeAttribute(hit.pos, "value", text);
  return systemTr(tr);
}

/**
 * 变量级填值:同变量全部原子一次写入;reference slot 不存在/值空白→null。
 * 返回受影响原子数(编辑器通知「同步 N 处」消费;0 视为失败)。
 */
export function setPlaceholderVariable(
  state: EditorState,
  slotId: string,
  value: string,
): { tr: Transaction; count: number } | null {
  const text = value.trim();
  if (!slotId || text === "") return null;
  const hits = findVariableHits(state.doc, slotId);
  if (hits.length === 0) return null;
  const tr = state.tr;
  for (const hit of hits) tr.setNodeAttribute(hit.pos, "value", text);
  return { tr: systemTr(tr), count: hits.length };
}
