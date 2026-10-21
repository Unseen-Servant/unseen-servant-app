import { invoke } from '@tauri-apps/api/core';
import { emit } from '@tauri-apps/api/event';
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

/** Asks for the app's settings modal, at General or at Help. Legend Lore
 *  hosts it for now, so this goes to every window and the one holding Legend
 *  Lore opens it. The Help menu (file_menu.rs) sends it too. */
export const OPEN_SETTINGS_EVENT = 'shell://open-settings';

export function openSettings(tab: 'general' | 'help' = 'general'): Promise<void> {
  return emit(OPEN_SETTINGS_EVENT, tab);
}

/** Asks this window's host to bring a tool forward in the rack, as Rust's
 *  show_panel does from the File menu: a chord that changes what a tool
 *  shows calls this before acting, so the change is seen. The main
 *  window's host answers; a panel in its own window is forward already, so
 *  there nobody listens and the call is a no-op. */
const showPanelListeners = new Set<(id: PanelId) => void>();

export function showPanel(id: PanelId): void {
  for (const listener of showPanelListeners) listener(id);
}

export function onShowPanel(listener: (id: PanelId) => void): () => void {
  showPanelListeners.add(listener);
  return () => {
    showPanelListeners.delete(listener);
  };
}
