// Legend Lore is the only tool so far; the root route hands off to it
// until the window registry (workstation architecture, step 2c) opens
// each tool's window on its own route.
import { redirect } from '@sveltejs/kit';

export function load() {
  redirect(307, '/legend-lore');
}
