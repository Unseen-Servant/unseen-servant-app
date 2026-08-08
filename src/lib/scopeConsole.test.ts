import { describe, expect, it } from 'vitest';
import { parseScopeConsoleState } from './scopeConsole';
import type { ScopeConsoleState } from './scopeConsole';

const FULL: ScopeConsoleState = {
  playing: ['Strahd'],
  mutedCollections: ['Homebrew'],
  soloedSystems: ['D&D 5E'],
  mutedSystems: ['unknown'],
  scopeSolos: [['/lib/bestiary', { kind: 'folder', label: 'bestiary' }]],
  scopeMutes: [['/lib/old.pdf', { kind: 'file', label: 'old.pdf' }]],
  curationSolos: ['collected'],
  curationMutes: [],
  hideOutOfScope: true,
};

describe('parseScopeConsoleState', () => {
  it('round-trips a full console through JSON', () => {
    expect(parseScopeConsoleState(JSON.parse(JSON.stringify(FULL)))).toEqual(FULL);
  });

  it('returns undefined for absent or non-object values', () => {
    expect(parseScopeConsoleState(undefined)).toBeUndefined();
    expect(parseScopeConsoleState(null)).toBeUndefined();
    expect(parseScopeConsoleState('nope')).toBeUndefined();
  });

  it('a corrupt field falls back alone — the rest of the console survives', () => {
    const mangled = { ...JSON.parse(JSON.stringify(FULL)), playing: 'not-an-array' };
    const out = parseScopeConsoleState(mangled)!;
    expect(out.playing).toEqual([]);
    expect(out.mutedCollections).toEqual(['Homebrew']);
    expect(out.hideOutOfScope).toBe(true);
  });

  it('drops malformed scope-ref entries but keeps well-formed ones', () => {
    const mangled = JSON.parse(JSON.stringify(FULL));
    mangled.scopeSolos.push(['/bad', { kind: 'nonsense', label: 3 }]);
    const out = parseScopeConsoleState(mangled)!;
    expect(out.scopeSolos).toEqual(FULL.scopeSolos);
  });

  it('drops curation keys outside the two-value domain', () => {
    const mangled = { ...JSON.parse(JSON.stringify(FULL)), curationSolos: ['collected', 'weird'] };
    expect(parseScopeConsoleState(mangled)!.curationSolos).toEqual(['collected']);
  });
});
