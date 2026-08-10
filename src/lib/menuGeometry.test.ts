import { describe, it, expect } from 'vitest';
import { clampToViewport } from './menuGeometry';

describe('clampToViewport', () => {
  const viewport = { width: 1000, height: 800 };
  const size = { width: 200, height: 300 };

  it('leaves a menu that already fits where it was asked to go', () => {
    expect(clampToViewport({ x: 100, y: 100 }, size, viewport)).toEqual({ x: 100, y: 100 });
  });

  it('pulls a menu back from the right edge', () => {
    // 900 + 200 would end at 1100, past the 1000 viewport.
    expect(clampToViewport({ x: 900, y: 100 }, size, viewport).x).toBe(792); // 1000 - 200 - 8
  });

  it('pulls a menu back from the bottom edge', () => {
    expect(clampToViewport({ x: 100, y: 700 }, size, viewport).y).toBe(492); // 800 - 300 - 8
  });

  it('holds the padding at the top-left edges', () => {
    expect(clampToViewport({ x: -50, y: -50 }, size, viewport)).toEqual({ x: 8, y: 8 });
  });

  it('clamps both axes at once in the bottom-right corner', () => {
    expect(clampToViewport({ x: 990, y: 790 }, size, viewport)).toEqual({ x: 792, y: 492 });
  });

  it('prefers the near edge when the menu is larger than the viewport', () => {
    // Nothing fits, so the far-edge pull would push it off the near side.
    // Showing the top-left is the useful half — that's where the rows start.
    const huge = { width: 1200, height: 900 };
    expect(clampToViewport({ x: 400, y: 400 }, huge, viewport)).toEqual({ x: 8, y: 8 });
  });

  it('honours a caller-supplied padding', () => {
    expect(clampToViewport({ x: 990, y: 100 }, size, viewport, 20).x).toBe(780);
  });

  it('places a menu that exactly fills the viewport at the padding', () => {
    const exact = { width: 984, height: 784 }; // 1000 - 16, 800 - 16
    expect(clampToViewport({ x: 500, y: 500 }, exact, viewport)).toEqual({ x: 8, y: 8 });
  });
});
