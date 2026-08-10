/**
 * Sort retrieval sources by score descending.
 * Sources with a missing/non-number score sort last (stable order preserved within groups).
 * Pure: returns a new array, does not mutate the input.
 */
export function sortSourcesByScore<T extends { score?: number }>(srcs: T[]): T[] {
  return [...srcs].sort((a, b) => {
    const sa = typeof a.score === "number" ? a.score : -Infinity;
    const sb = typeof b.score === "number" ? b.score : -Infinity;
    return sb - sa;
  });
}
