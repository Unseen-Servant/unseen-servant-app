// Rows of a Command context menu (CommandMenu.svelte).

export type MenuItem =
  // `lamp`: a choice row whose pip says whether it's the one in effect.
  // `chord`: the binding (keybindings.ts) whose key does the same on the
  // selected row, shown as its hint.
  | { kind: 'action'; label: string; danger?: boolean; lamp?: boolean; chord?: string; action: () => void }
  | { kind: 'heading'; label: string }
  // `picks`: choices side by side in one row, each a swatch of the plate it
  // fills (null for none), its name only a tooltip (app.css .menu-picks).
  | { kind: 'picks'; label: string; picks: Pick[] }
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
export const keyed = (label: string, chord: string, run: () => void): MenuItem => ({
  kind: 'action',
  label,
  action: run,
  chord,
});
export const heading = (label: string): MenuItem => ({ kind: 'heading', label });
export const choice = (label: string, on: boolean, run: () => void): MenuItem => ({
  kind: 'action',
  label,
  action: run,
  lamp: on,
});
export const picks = (label: string, picks: Pick[]): MenuItem => ({ kind: 'picks', label, picks });
export const divider: MenuItem = { kind: 'divider' };
