// The tool panels, in the rack bar's order (contract: PANELS.md). Rust keeps
// its own copy of the ids with each window's default size, in
// src-tauri/src/panels.rs, because it creates the windows. `rackMin` is the
// smallest slot the main window's rack gives a panel — under a pop-out
// window's minimum, so that two tools fit side by side. A `compact` tool
// opens at its smallest: mounted from the rack bar it takes a column of
// rackMin.w, its box in the rack is no taller than rackMin.h (bare rack
// below), and its pop-out opens at the window's minimum.

export const PANELS = [
  { id: 'legend-lore', title: 'Legend Lore', rackMin: { w: 560, h: 320 }, compact: false },
  { id: 'command', title: 'Command', rackMin: { w: 420, h: 280 }, compact: false },
  { id: 'augury', title: 'Augury', rackMin: { w: 270, h: 391 }, compact: true },
  { id: 'servant', title: 'Servant', rackMin: { w: 380, h: 280 }, compact: false },
] as const;

export type PanelId = (typeof PANELS)[number]['id'];

export function isPanelId(id: string): id is PanelId {
  return PANELS.some((p) => p.id === id);
}

export function panelTitle(id: PanelId): string {
  return PANELS.find((p) => p.id === id)!.title;
}
