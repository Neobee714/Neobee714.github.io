import os from 'node:os';
import path from 'node:path';

function normalizeWindowsDrivePath(input: string): string {
  const match = input.match(/^([A-Za-z]):[\\/](.*)$/);
  if (!match) return input;

  const drive = match[1].toLowerCase();
  const rest = match[2].replace(/\\/g, '/');
  return `/mnt/${drive}/${rest}`;
}

export function resolveVaultPath(raw?: string): string {
  const candidate = (raw || './vault').trim();
  const runningInWsl = os.release().toLowerCase().includes('microsoft');
  const normalized = runningInWsl ? normalizeWindowsDrivePath(candidate) : candidate;
  return path.resolve(normalized);
}

