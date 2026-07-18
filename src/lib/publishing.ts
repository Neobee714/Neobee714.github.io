const DRAFT_STATUS_VALUES = new Set(['进行中', 'draft', 'wip', 'writing']);
const LOCKED_STATUS_VALUES = new Set(['已锁住', 'locked']);

export function normalizeFrontmatterScalar(raw: unknown): string {
  const value = String(raw ?? '').trim();
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1).trim();
    }
  }
  return value;
}

export function hasPublishFlag(raw: unknown): boolean {
  if (raw === true) return true;
  return ['true', 'yes', '是'].includes(normalizeFrontmatterScalar(raw).toLowerCase());
}

export function normalizeStatus(raw: unknown): string {
  return normalizeFrontmatterScalar(raw).toLowerCase();
}

export function isDraftStatus(raw: unknown): boolean {
  return DRAFT_STATUS_VALUES.has(normalizeStatus(raw));
}

export function isLockedStatus(raw: unknown): boolean {
  return LOCKED_STATUS_VALUES.has(normalizeStatus(raw));
}
