import { describe, it, expect, beforeEach } from 'vitest';
import {
  TREE_PATHS_MIME,
  isTreePathsDrag,
  describeTreePathsDrag,
  writeTreePathsTransfer,
  setTreePathsPayload,
  getTreePathsPayload,
  clearTreePathsPayload,
  type DataTransferLike,
} from './dragPayload';

function stubTransfer(): DataTransferLike & { data: Record<string, string> } {
  return {
    effectAllowed: 'none',
    data: {} as Record<string, string>,
    setData(format: string, value: string) {
      this.data[format] = value;
    },
  };
}

describe('isTreePathsDrag', () => {
  it('recognises our own drag', () => {
    expect(isTreePathsDrag([TREE_PATHS_MIME, 'text/plain'])).toBe(true);
  });

  it('matches case-insensitively, since browsers lowercase .types', () => {
    expect(isTreePathsDrag(['APPLICATION/X-LEGENDLORE-TREE-PATHS'])).toBe(true);
  });

  it('rejects a plain text drag, an OS file drag, and no drag at all', () => {
    expect(isTreePathsDrag(['text/plain'])).toBe(false);
    expect(isTreePathsDrag(['Files'])).toBe(false);
    expect(isTreePathsDrag([])).toBe(false);
    expect(isTreePathsDrag(undefined)).toBe(false);
    expect(isTreePathsDrag(null)).toBe(false);
  });
});

describe('describeTreePathsDrag', () => {
  // Silently filing 47 books is the one way this gesture can feel unsafe.
  it('names the count for a multi-file drag', () => {
    expect(describeTreePathsDrag({ paths: ['/a.pdf', '/b.pdf'], label: 'Adventures' })).toBe(
      'Adventures (2 files)'
    );
  });

  it('leaves a single file unadorned', () => {
    expect(describeTreePathsDrag({ paths: ['/a.pdf'], label: 'Curse of Strahd' })).toBe(
      'Curse of Strahd'
    );
  });
});

describe('writeTreePathsTransfer', () => {
  it('stamps the marker MIME and a human-readable fallback', () => {
    const dt = stubTransfer();
    writeTreePathsTransfer(dt, { paths: ['/a.pdf', '/b.pdf'], label: 'Adventures' });
    expect(Object.keys(dt.data)).toContain(TREE_PATHS_MIME);
    expect(dt.data['text/plain']).toBe('Adventures (2 files)');
    expect(dt.effectAllowed).toBe('copy');
  });

  it('produces types that isTreePathsDrag accepts', () => {
    const dt = stubTransfer();
    writeTreePathsTransfer(dt, { paths: ['/a.pdf'], label: 'a' });
    expect(isTreePathsDrag(Object.keys(dt.data))).toBe(true);
  });
});

describe('the payload store', () => {
  beforeEach(() => clearTreePathsPayload());

  it('starts empty', () => {
    expect(getTreePathsPayload()).toBeNull();
  });

  it('round-trips a payload', () => {
    setTreePathsPayload({ paths: ['/a.pdf'], label: 'a' });
    expect(getTreePathsPayload()).toEqual({ paths: ['/a.pdf'], label: 'a' });
  });

  it('is null again after clearing', () => {
    setTreePathsPayload({ paths: ['/a.pdf'], label: 'a' });
    clearTreePathsPayload();
    expect(getTreePathsPayload()).toBeNull();
  });
});
