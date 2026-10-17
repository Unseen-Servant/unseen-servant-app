import { invoke } from '@tauri-apps/api/core';
import { readable } from 'svelte/store';

// The workstation's machinery as the status bar's lamps show it: the
// sidecar, the embedding runtime and its model, the MCP link. Polled while
// anything in the window subscribes, so Legend Lore and the status bar
// share one poller per window.

export interface Machinery {
  sidecarConnected: boolean;
  // Runtime (the process answers) vs. ready (it also has the model): the
  // remedies differ — launch the runtime vs. pull the model.
  embedderRunning: boolean;
  embedderReady: boolean;
  mcpConnected: boolean;
  mcpActive: boolean;
}

const HEALTH_MS = 10_000;
// Faster, so the active-query pulse is caught: the backend keeps the active
// flag for 5s after a query.
const MCP_MS = 5_000;

const DOWN: Machinery = {
  sidecarConnected: false,
  embedderRunning: false,
  embedderReady: false,
  mcpConnected: false,
  mcpActive: false,
};

export const machinery = readable<Machinery>(DOWN, (set) => {
  let state = DOWN;
  const put = (patch: Partial<Machinery>) => set((state = { ...state, ...patch }));

  async function sidecar() {
    try {
      put({ sidecarConnected: await invoke<boolean>('check_sidecar_health') });
    } catch {
      put({ sidecarConnected: false });
    }
  }

  async function embedder() {
    try {
      const status = await invoke<{
        models: { role: string; runtime_up: boolean; ready: boolean }[];
      }>('check_models_status');
      const embed = status.models.find((m) => m.role === 'embed');
      put({ embedderRunning: embed?.runtime_up ?? false, embedderReady: embed?.ready ?? false });
    } catch {
      put({ embedderRunning: false, embedderReady: false });
    }
  }

  async function mcp() {
    try {
      const status = await invoke<{ connected: boolean; active: boolean }>('check_mcp_status');
      put({ mcpConnected: status.connected, mcpActive: status.active });
    } catch {
      put({ mcpConnected: false, mcpActive: false });
    }
  }

  const health = () => {
    void sidecar();
    void embedder();
  };
  health();
  void mcp();
  const timers = [setInterval(health, HEALTH_MS), setInterval(mcp, MCP_MS)];
  return () => timers.forEach(clearInterval);
});
