// The tool panels, in tab order (contract: PANELS.md). Rust keeps its own
// copy of the ids with each window's default size, in src-tauri/src/panels.rs,
// because it creates the windows.

export const PANELS = [
  { id: 'legend-lore', title: 'Legend Lore' },
  { id: 'command', title: 'Command' },
  { id: 'servant', title: 'Servant' },
] as const;

export type PanelId = (typeof PANELS)[number]['id'];

export function isPanelId(id: string): id is PanelId {
  return PANELS.some((p) => p.id === id);
}

export function panelTitle(id: PanelId): string {
  return PANELS.find((p) => p.id === id)!.title;
}
