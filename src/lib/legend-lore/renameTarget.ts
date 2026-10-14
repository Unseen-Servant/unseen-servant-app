// What a rename in the tree or the systems view commits. The field shows a
// file's name without its extension, so the extension comes back on commit
// unless it was typed anyway. A name with nothing before the extension (a
// hidden dotfile) or the name as it was is no rename at all: the field
// just closes, rather than the disk refusing a name that "already exists".

/** The full new name, or null when there's nothing to rename. */
export function renameTarget(original: string, typed: string, isDir: boolean): string | null {
  const name = typed.trim();
  const ext = isDir ? '' : (original.match(/\.[^.]+$/)?.[0] ?? '');
  const typedExt = ext !== '' && name.toLowerCase().endsWith(ext.toLowerCase());
  const stem = (typedExt ? name.slice(0, -ext.length) : name).trim();
  if (!stem) return null;
  const full = stem + (typedExt ? name.slice(-ext.length) : ext);
  return full === original ? null : full;
}
