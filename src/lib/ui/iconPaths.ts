/**
 * Path data for the glyphs drawn at more than one call site.
 *
 * Each surface keeps its own <svg> wrapper — the size, fill and state rules
 * live in the component that owns the row, chip or badge. Only the shape is
 * shared, so a vendor bump touches one line instead of thirty-four.
 *
 * Single-use glyphs stay inline; they have nothing to drift against.
 *
 * Font Awesome Free 7.x glyphs (version in each file) are vendored under ./icons and checked
 * against these constants by iconPaths.test.ts. CC BY 4.0, Fonticons, Inc.
 */

/** Font Awesome "book". viewBox="0 0 640 640". Source: ./icons/book-solid-full.svg */
export const BOOK =
  'M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z';

/**
 * Font Awesome "folder" and "folder-open". viewBox="0 0 640 640". Drawn as a
 * pair in one <svg> — classes .folder-shut and .folder-opened — so the folder
 * opens while its button is hovered; see "Folder glyph" in app.css.
 * Sources: ./icons/folder-solid-full.svg, ./icons/folder-open-solid-full.svg
 */
export const FOLDER =
  'M128 512L512 512C547.3 512 576 483.3 576 448L576 208C576 172.7 547.3 144 512 144L362.7 144C355.8 144 349 141.8 343.5 137.6L305.1 108.8C294 100.5 280.5 96 266.7 96L128 96C92.7 96 64 124.7 64 160L64 448C64 483.3 92.7 512 128 512z';

export const FOLDER_OPEN =
  'M88 289.6L64.4 360.2L64.4 160C64.4 124.7 93.1 96 128.4 96L267.1 96C280.9 96 294.4 100.5 305.5 108.8L343.9 137.6C349.4 141.8 356.2 144 363.1 144L480.4 144C515.7 144 544.4 172.7 544.4 208L544.4 224L179 224C137.7 224 101 250.4 87.9 289.6zM509.8 512L131 512C98.2 512 75.1 479.9 85.5 448.8L133.5 304.8C140 285.2 158.4 272 179 272L557.8 272C590.6 272 613.7 304.1 603.3 335.2L555.3 479.2C548.8 498.8 530.4 512 509.8 512z';

/**
 * Font Awesome "caret-right". Disclosure arrows draw it through the .caret
 * rule in app.css, which turns it a quarter down while open. Drawn with
 * viewBox="96 64 512 512" — the vendored 640 box recentred on the glyph, so
 * the rotation pivots in place. Source: ./icons/caret-right-solid-full.svg
 */
export const CARET_RIGHT =
  'M441.3 299.8C451.5 312.4 450.8 330.9 439.1 342.6L311.1 470.6C301.9 479.8 288.2 482.5 276.2 477.5C264.2 472.5 256.5 460.9 256.5 448L256.5 192C256.5 179.1 264.3 167.4 276.3 162.4C288.3 157.4 302 160.2 311.2 169.3L439.2 297.3L441.4 299.7z';

/**
 * Bookmark ribbon, hollow — always stroked, never filled (stroke-width 2.2).
 * A collection's ribbon is stroked in its pigment; one without a pigment,
 * and the "in a collection" bucket, in tertiary grey; Loose dashes it.
 * viewBox="0 0 24 24".
 */
export const RIBBON_OUTLINE = 'M6 3h12v18l-6-4.4L6 21z';

/**
 * Heater shield — a game system. Always stroked, never filled: systems are
 * monochrome and carry no colour of their own. The Untagged bucket draws the
 * same shield dashed (a placeholder, not an identity), as Loose does with the
 * collection ribbon. viewBox="0 0 24 24", stroke-width="2.2".
 */
export const SHIELD = 'M12 3l7 2.5V11c0 5-3.3 8.2-7 10-3.7-1.8-7-5-7-10V5.5z';
