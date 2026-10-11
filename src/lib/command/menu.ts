// Rows of a Command context menu (CommandMenu.svelte).

export type MenuItem =
  | { kind: 'action'; label: string; danger?: boolean; action: () => void }
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
export const divider: MenuItem = { kind: 'divider' };
