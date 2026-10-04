import { error } from '@sveltejs/kit';
import { isPanelId } from '../../../lib/shell/panels';
import type { PageLoad } from './$types';

// A panel popped out into its own window (src-tauri/src/panels.rs opens it).
export const load: PageLoad = ({ params }) => {
  if (!isPanelId(params.id)) error(404, `Unknown panel: ${params.id}`);
  return { id: params.id };
};
