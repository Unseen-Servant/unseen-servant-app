// Rows of a Command context menu (CommandMenu.svelte).

export type MenuItem =
  // `lamp`: a choice row whose pip says whether it's the one in effect.
  // `chord`: the binding (keybindings.ts) whose key does the same on the
  // selected row, shown as its hint. `swatch`: a pigment the row names,
  // drawn as the strip it gives a track's nameplate.
  | { kind: 'action'; label: string; danger?: boolean; lamp?: boolean; chord?: string; swatch?: string; action: () => void }
  | { kind: 'heading'; label: string }
  | { kind: 'divider' };

export interface OpenMenu {
  x: number;
  y: number;
  items: MenuItem[];
}

export const action = (label: string, run: () => void, danger = false): MenuItem => ({
  kind: 'action',
  label,
  action: run,
  danger,
});
/** An action the selected row also takes from a key, as Legend Lore's
 *  menus carry their rows' keys. */
export const keyed = (label: string, chord: string, run: () => void): MenuItem => ({
  kind: 'action',
  label,
  action: run,
  chord,
});
export const heading = (label: string): MenuItem => ({ kind: 'heading', label });
export const choice = (label: string, on: boolean, run: () => void, swatch?: string): MenuItem => ({
  kind: 'action',
  label,
  action: run,
  lamp: on,
  swatch,
});
export const divider: MenuItem = { kind: 'divider' };
