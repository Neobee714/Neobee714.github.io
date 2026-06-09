const DRAFT_STATUS_VALUES = new Set(['进行中', 'draft', 'wip', 'writing']);
const LOCKED_STATUS_VALUES = new Set(['已锁住', 'locked']);

export function normalizeFrontmatterScalar(raw: string | undefined | null): string {
  const value = (raw ?? '').trim();
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1).trim();
    }
  }
  return value;
}

export function normalizeStatus(raw: string | undefined | null): string {
  return normalizeFrontmatterScalar(raw).toLowerCase();
}

export function isDraftStatus(raw: string | undefined | null): boolean {
  return DRAFT_STATUS_VALUES.has(normalizeStatus(raw));
}

export function isLockedStatus(raw: string | undefined | null): boolean {
  return LOCKED_STATUS_VALUES.has(normalizeStatus(raw));
}
