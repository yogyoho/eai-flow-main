// Vendored from semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8 explorer/src/store/edgePairKeys.js + edgePairKeys.d.ts (MIT)
// EAI adaptation: the upstream pair is a plain .js module + sibling .d.ts; merged into one .ts here.

export function pairRegistryKey(source: string, target: string): string {
  return JSON.stringify([source, target]);
}

export function curveGroupForPair(source: string, target: string): string {
  return JSON.stringify([source, target]);
}
