import { invoke } from '@tauri-apps/api/core';
import { rustMirror } from './rustMirror';
import type { PanelId } from './panels';

// Workstation state every window shares. Rust is the source of truth
// (src-tauri/src/app_context.rs, panels.rs); these stores only mirror it.

export interface AppContext {
  seq: number;
  campaign: string | null;
  session: string | null;
}

export interface PoppedPanels {
  seq: number;
  popped: PanelId[];
}

export const appContext = rustMirror<AppContext>(
  'app-context://changed',
  'get_app_context',
  { seq: 0, campaign: null, session: null },
);

export const poppedPanels = rustMirror<PoppedPanels>(
  'panels://changed',
  'get_popped_panels',
  { seq: 0, popped: [] },
);

export function setCampaign(campaign: string | null): Promise<void> {
  return invoke('set_active_campaign', { campaign });
}

export function setSession(session: string | null): Promise<void> {
  return invoke('set_active_session', { session });
}

export function popOut(id: PanelId): Promise<void> {
  return invoke('pop_out_panel', { id });
}

export function dock(id: PanelId): Promise<void> {
  return invoke('dock_panel', { id });
}
