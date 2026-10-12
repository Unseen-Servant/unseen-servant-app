// Rows of a Command context menu (CommandMenu.svelte).

export type MenuItem =
  // `lamp`: a choice row whose pip says whether it's the one in effect.
  | { kind: 'action'; label: string; danger?: boolean; lamp?: boolean; action: () => void }
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
export const heading = (label: string): MenuItem => ({ kind: 'heading', label });
export const choice = (label: string, on: boolean, run: () => void): MenuItem => ({
  kind: 'action',
  label,
  action: run,
  lamp: on,
});
export const divider: MenuItem = { kind: 'divider' };
