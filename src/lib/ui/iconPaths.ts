/**
 * Path data for the glyphs drawn at more than one call site.
 *
 * Each surface keeps its own <svg> wrapper — the size, fill and state rules
 * live in the component that owns the row, chip or badge. Only the shape is
 * shared, so a vendor bump touches one line instead of thirty-four.
 *
 * Single-use glyphs stay inline; they have nothing to drift against.
 *
 * Font Awesome Free 7.2.0 glyphs are vendored under ./icons and checked
 * against these constants by iconPaths.test.ts. CC BY 4.0, Fonticons, Inc.
 */

/** Font Awesome "book". viewBox="0 0 640 640". Source: ./icons/book-solid-full.svg */
export const BOOK =
  'M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z';

/**
 * Folder, solid, in two parts: FOLDER_BACK (panel and tab) and FOLDER_FLAP (the
 * front) drawn in one <svg>. Give the flap the global .folder-flap class and it
 * tips open while its button is hovered — see "Folder glyph" in app.css.
 * viewBox="0 0 24 24", fill="currentColor".
 */
export const FOLDER_BACK = 'M2 5h6l2 2h10v12H2z';
export const FOLDER_FLAP = 'M2 12h18v7H2z';

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

/**
 * The fess — a band across the shield, wall to wall where its sides stop
 * running straight. Drawn in the same <svg> as SHIELD when the system is
 * soloed: the shield taking up its charge is the active state.
 */
export const SHIELD_FESS = 'M5 11h14';
