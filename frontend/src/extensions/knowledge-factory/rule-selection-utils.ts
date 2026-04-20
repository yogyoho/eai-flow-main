export function toggleRuleSelection(selectedRuleIds: string[], ruleId: string): string[] {
  return selectedRuleIds.includes(ruleId)
    ? selectedRuleIds.filter((id) => id !== ruleId)
    : [...selectedRuleIds, ruleId];
}

export function getAllSelectedRuleIds(ruleIds: string[], selectedRuleIds: string[]): string[] {
  const allSelected = ruleIds.length > 0 && ruleIds.every((ruleId) => selectedRuleIds.includes(ruleId));
  return allSelected ? selectedRuleIds.filter((id) => !ruleIds.includes(id)) : Array.from(new Set([...selectedRuleIds, ...ruleIds]));
}

export function areAllRulesSelected(ruleIds: string[], selectedRuleIds: string[]): boolean {
  return ruleIds.length > 0 && ruleIds.every((ruleId) => selectedRuleIds.includes(ruleId));
}
