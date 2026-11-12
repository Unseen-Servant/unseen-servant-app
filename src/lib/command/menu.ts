// Rows of a Command context menu (CommandMenu.svelte).

export type MenuItem =
  // `lamp`: a choice row whose pip says whether it's the one in effect.
  // `chord`: the binding (keybindings.ts) whose key does the same on the
  // selected row, shown as its hint.
  | { kind: 'action'; label: string; danger?: boolean; lamp?: boolean; chord?: string; action: () => void }
  // `swatch`: a chip of the group's track colour, null for the empty
  // outline of a track without one; none for a heading that isn't a
  // track's. `add`: a + at the heading's end that adds to its group.
  | { kind: 'heading'; label: string; swatch?: string | null; add?: { label: string; run: () => void } }
  // `picks`: choices side by side in one row, each a swatch of the plate it
  // fills (null for none), its name only a tooltip (app.css .menu-picks).
  | { kind: 'picks'; label: string; picks: Pick[] }
  // `submenu`: a row that opens its actions beside the menu, as Legend
  // Lore's Send to Command does.
  | { kind: 'submenu'; label: string; items: MenuItem[] }
  | { kind: 'divider' };

export interface Pick {
  label: string;
  swatch: string | null;
  on: boolean;
  action: () => void;
}

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
export const keyed = (label: string, chord: string, run: () => void, danger = false): MenuItem => ({
  kind: 'action',
  label,
  action: run,
  chord,
  danger,
});
export const heading = (label: string, more: { swatch?: string | null; add?: { label: string; run: () => void } } = {}): MenuItem => ({
  kind: 'heading',
  label,
  ...more,
});
export const choice = (label: string, on: boolean, run: () => void): MenuItem => ({
  kind: 'action',
  label,
  action: run,
  lamp: on,
});
export const picks = (label: string, picks: Pick[]): MenuItem => ({ kind: 'picks', label, picks });
export const submenu = (label: string, items: MenuItem[]): MenuItem => ({ kind: 'submenu', label, items });
export const divider: MenuItem = { kind: 'divider' };
