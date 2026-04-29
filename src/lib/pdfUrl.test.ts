import { describe, it, expect } from 'vitest';
import { pdfFileUrl, pageHint } from './pdfUrl';

describe('pdfFileUrl', () => {
  it('builds a plain file URL for a POSIX path with no page', () => {
    expect(pdfFileUrl('/Users/jay/Books/SRD.pdf'))
      .toBe('file:///Users/jay/Books/SRD.pdf');
  });

  it('appends #page=N when a page is provided', () => {
    expect(pdfFileUrl('/Users/jay/Books/SRD.pdf', 42))
      .toBe('file:///Users/jay/Books/SRD.pdf#page=42');
  });

  it('omits the fragment when page is null/undefined/0/negative', () => {
    const path = '/Users/jay/Books/SRD.pdf';
    expect(pdfFileUrl(path, null)).toBe('file:///Users/jay/Books/SRD.pdf');
    expect(pdfFileUrl(path, undefined)).toBe('file:///Users/jay/Books/SRD.pdf');
    expect(pdfFileUrl(path, 0)).toBe('file:///Users/jay/Books/SRD.pdf');
    expect(pdfFileUrl(path, -1)).toBe('file:///Users/jay/Books/SRD.pdf');
  });

  it('percent-encodes spaces and special chars in path segments', () => {
    expect(pdfFileUrl('/Users/jay/My Books/Black Flag.pdf', 5))
      .toBe('file:///Users/jay/My%20Books/Black%20Flag.pdf#page=5');
  });

  it('handles Windows drive-letter paths with backslashes', () => {
    expect(pdfFileUrl('C:\\Users\\jay\\SRD.pdf', 12))
      .toBe('file:///C:/Users/jay/SRD.pdf#page=12');
  });

  it('handles Windows drive-letter paths with forward slashes', () => {
    expect(pdfFileUrl('C:/Users/jay/SRD.pdf', 12))
      .toBe('file:///C:/Users/jay/SRD.pdf#page=12');
  });
});

describe('pageHint', () => {
  it('returns empty string when no page metadata', () => {
    expect(pageHint()).toBe('');
    expect(pageHint(null, null)).toBe('');
    expect(pageHint(0, 0)).toBe('');
  });

  it('formats single-page hints as p.N', () => {
    expect(pageHint(5)).toBe('p.5');
    expect(pageHint(5, 5)).toBe('p.5');
  });

  it('formats multi-page hints as pp.N–M with en-dash', () => {
    expect(pageHint(5, 7)).toBe('pp.5–7');
  });

  it('treats missing pageEnd as single-page', () => {
    expect(pageHint(12, null)).toBe('p.12');
    expect(pageHint(12, undefined)).toBe('p.12');
  });
});
