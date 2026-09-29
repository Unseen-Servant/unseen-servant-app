import { describe, it, expect } from 'vitest';
import { pdfFileUrl, pageHint, pageCitation, bookTitle } from './pdfUrl';

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

describe('pageCitation', () => {
  it('leads with the printed label when it is known', () => {
    expect(pageCitation(324, 331, '326', '333')).toBe('pp.326–333');
    expect(pageCitation(24, 24, '12', '12')).toBe('p.12');
    expect(pageCitation(24, 24, '12', '')).toBe('p.12');
  });

  it('falls back to the physical span when a multi-page span has no end label', () => {
    // Labels are sparse — a labelled page running into unlabelled ones
    // must not be cited as that one printed page.
    expect(pageCitation(24, 26, '12', '')).toBe('pp.24–26');
    expect(pageCitation(24, 26, '12')).toBe('pp.24–26');
  });

  it('falls back to the physical span when the labels are blank', () => {
    expect(pageCitation(24, 26, '', '')).toBe('pp.24–26');
    expect(pageCitation(24, 24)).toBe('p.24');
    expect(pageCitation(0, 0, '', '')).toBe('');
  });
});

describe('bookTitle', () => {
  it('drops the .pdf extension, any case, and nothing else', () => {
    expect(bookTitle('OSRIC_2E.pdf')).toBe('OSRIC_2E');
    expect(bookTitle('Wight-Box_PDF_1.3.PDF')).toBe('Wight-Box_PDF_1.3');
    expect(bookTitle('notes.pdf.txt')).toBe('notes.pdf.txt');
  });
});
