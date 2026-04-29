/**
 * Build a `file://` URL for opening a PDF, optionally anchored to a page
 * via the standard PDF Open Parameters fragment (`#page=N`).
 *
 * Honour: viewers honouring the fragment (Adobe Reader, PDF Expert, Skim,
 * browser-based PDF viewers) jump to the requested page. Viewers that
 * ignore it (notably macOS Preview) silently open at page 1 — see #113.
 *
 * Cross-platform path handling:
 *   - POSIX absolute paths (`/Users/...`)            → `file:///Users/...`
 *   - Windows drive paths (`C:\path` or `C:/path`)   → `file:///C:/path`
 *
 * URL constructor handles percent-encoding of spaces and other special
 * chars in path segments; we don't reinvent that here.
 */
export function pdfFileUrl(absolutePath: string, page?: number | null): string {
  const forwardSlashed = absolutePath.replace(/\\/g, '/');
  const isWindowsDrive = /^[a-zA-Z]:/.test(forwardSlashed);
  const prefix = isWindowsDrive ? 'file:///' : 'file://';
  const url = new URL(prefix + forwardSlashed);
  if (page && page > 0) {
    // PDF Open Parameters spec: `#page=N` (1-indexed).
    url.hash = `page=${page}`;
  }
  return url.toString();
}

/**
 * Format a page hint for tooltip / aria-label use.
 * Returns `"p.5"`, `"pp.5–7"`, or `""` when no page metadata is present.
 */
export function pageHint(pageStart?: number | null, pageEnd?: number | null): string {
  if (!pageStart || pageStart <= 0) return '';
  if (!pageEnd || pageEnd === pageStart) return `p.${pageStart}`;
  return `pp.${pageStart}–${pageEnd}`;
}
