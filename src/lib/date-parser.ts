/**
 * Flexible date parser for Obsidian frontmatter.
 *
 * Supports:
 *   - ISO 8601          -> "2026-01-03" / "2026-01-03T12:00:00Z"
 *   - Chinese format    -> "2026年1月3日" / "2026年01月03日"
 *   - Slash / dash      -> "2026/1/3"  / "2026-1-3"
 *
 * Returns a UTC-midnight `Date` on success, `undefined` on failure.
 *
 * Implements REQ-04-2 from requirements.md.
 */

const CHINESE_DATE = /^\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*$/;
const NUMERIC_DATE = /^\s*(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})\s*$/;

export function parseFlexDate(input: unknown): Date | undefined {
  if (input instanceof Date) {
    return Number.isNaN(input.getTime()) ? undefined : input;
  }

  if (typeof input !== 'string') {
    return undefined;
  }

  const s = input.trim();
  if (!s) {
    return undefined;
  }

  // Strategy 1: Chinese format (check first; JS Date does not parse this)
  const cn = s.match(CHINESE_DATE);
  if (cn) {
    const [, y, mo, d] = cn;
    return buildUtcDate(+y, +mo, +d);
  }

  // Strategy 2: numeric with / or - or .
  const num = s.match(NUMERIC_DATE);
  if (num) {
    const [, y, mo, d] = num;
    return buildUtcDate(+y, +mo, +d);
  }

  // Strategy 3: fall back to native Date for ISO 8601 / RFC 2822 / etc.
  const native = new Date(s);
  if (!Number.isNaN(native.getTime())) {
    return native;
  }

  return undefined;
}

function buildUtcDate(year: number, month: number, day: number): Date | undefined {
  if (month < 1 || month > 12) return undefined;
  if (day < 1 || day > 31) return undefined;

  const d = new Date(Date.UTC(year, month - 1, day));
  // Guard against overflow like month=2, day=30 -> becomes March 2.
  if (
    d.getUTCFullYear() !== year ||
    d.getUTCMonth() !== month - 1 ||
    d.getUTCDate() !== day
  ) {
    return undefined;
  }
  return d;
}
