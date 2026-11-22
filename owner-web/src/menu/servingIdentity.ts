/**
 * How the owner tells servings apart, ported from android/.../data/owner/OwnerServingIdentity.kt and
 * android/.../ui/common/ServingLabels.kt.
 *
 * Servings are told apart by volume, not by the menu's word for a serving: "잔 30ml" and "샷 30ml" are the same
 * serving, 60ml is another. Korean "병" and English "Bottle" are one bottle, whatever capacity is printed.
 */
const BOTTLE_WITH_SIZE = /^(?:병|bottle)\s*\(?\s*\d{1,4}(?:\.\d+)?\s*(?:ml|l)\s*\)?$/i;

export function isBottleServingLabel(label: string | null | undefined): boolean {
  const normalized = label?.trim().toLowerCase();
  if (normalized === undefined) return false;
  return normalized === "병" || normalized === "bottle" || BOTTLE_WITH_SIZE.test(normalized);
}

export function canonicalServingLabel(label: string | null | undefined): string | null {
  const trimmed = label?.trim();
  if (trimmed === undefined) return null;
  return isBottleServingLabel(trimmed) ? "Bottle" : trimmed;
}

/** One non-bottle option per ml, whatever its label; an option without a pour cannot be told apart by a label. */
export function servingIdentityKey(pourMl: number | null | undefined, label: string | null | undefined): string {
  if (isBottleServingLabel(label)) return "bottle";
  if (pourMl !== null && pourMl !== undefined) return `ml:${pourMl}`;
  return "ml:unspecified";
}

/** ServingLabels.kt `servingDisplayLabel`: "Bottle", "30ml", or the label as written. */
export function servingDisplayLabel(pourMl: number | null, optionLabel: string | null): string {
  const raw = optionLabel?.trim() ?? "";
  if (isBottleServingLabel(raw)) return "Bottle";
  if (pourMl !== null) return `${pourMl}ml`;
  return raw;
}
