import { writable } from 'svelte/store';

// One confirmation prompt for the whole app. A single <ConfirmDialog> is
// mounted at page level and renders whatever this store holds, so raising
// a prompt costs one await at the call site:
//
//   if (!(await confirmPrompt.request({ title: 'Delete file', danger: true }))) return;
//
// That ergonomic matters more than it looks: the previous shape needed a
// page-level state variable plus a conditional block per call site, which
// is why the file-tree handlers reached for the native OS dialog instead.
// See docs/specs/ui/2026-08-11-modal-audit-design.md.

/**
 * One line of a confirmation's readout — the app's habit of answering "how
 * much" with a figure rather than an adjective, applied to damage.
 *
 * `to` is what the value becomes, when it changes. `unchanged` marks a `to`
 * that is a reassurance rather than damage ("untouched", "Loose") so the
 * dialog renders it calm instead of in the prompt's tone — the caller states
 * what the value means and the dialog decides how that looks.
 */
export interface ConfirmRow {
  label: string;
  value: string;
  to?: string;
  unchanged?: boolean;
}

export interface ConfirmRequest {
  title: string;
  message?: string;
  rows?: ConfirmRow[];
  confirmLabel?: string;
  cancelLabel?: string;
  // Destructive prompts auto-focus Cancel and paint the confirm in
  // --text-danger. The dialog owns both behaviors; this is just the flag.
  danger?: boolean;
}

export function createConfirmStore() {
  const { subscribe, set } = writable<ConfirmRequest | null>(null);

  let pending: ((value: boolean) => void) | null = null;

  function request(req: ConfirmRequest): Promise<boolean> {
    // A second prompt while one is open is a race, not a reachable flow —
    // the browser inerts the page behind an open <dialog>. Resolve the
    // outstanding one rather than dropping it: an await that never settles
    // strands the caller mid-way through whatever it was updating.
    pending?.(false);
    return new Promise<boolean>((resolve) => {
      pending = resolve;
      set(req);
    });
  }

  function answer(value: boolean) {
    const resolve = pending;
    pending = null;
    set(null);
    resolve?.(value);
  }

  return { subscribe, request, answer };
}

export const confirmPrompt = createConfirmStore();
