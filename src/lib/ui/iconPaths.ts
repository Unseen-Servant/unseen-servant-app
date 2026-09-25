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

/** Font Awesome "dice-d6". viewBox="0 0 640 640". Source: ./icons/dice-d6-solid-full.svg */
export const DICE_D6 =
  'M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z';

/** Font Awesome "book". viewBox="0 0 640 640". Source: ./icons/book-solid-full.svg */
export const BOOK =
  'M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z';

/**
 * Font Awesome "folder-open", re-fitted: upstream ships a 576x512 viewBox that
 * clipped both side edges. The glyph only reads correctly inside
 * FOLDER_OPEN_VIEWBOX, which centres it on the 640 grid the other icons use —
 * pass the two together. Not vendored; do not "restore" it from upstream.
 */
export const FOLDER_OPEN_VIEWBOX = '-24 -60 640 640';

export const FOLDER_OPEN =
  'M88.7 223.8L0 375.8L0 96C0 60.7 28.7 32 64 32L181.5 32C198.5 32 214.8 38.7 226.7 50.7L269.3 93.3C281.3 105.3 297.6 112 314.5 112L448 112C483.3 112 512 140.7 512 176L512 208L144 208C121.4 208 100.6 220 88.7 223.8zM144 240L560 240C572.1 240 583.3 246.8 588.9 257.6C594.5 268.4 593.5 281.4 586.4 291.2L501.9 467.2C495.3 480.6 481.6 488 467.2 488L48 488C36 488 24.8 481.2 19.2 470.4C13.6 459.6 14.6 446.6 21.7 436.8L106.2 260.8C112.8 247.4 126.5 240 144 240z';

/** Bookmark ribbon, filled — a collection keeps its pigment. viewBox="0 0 24 24". */
export const RIBBON_FILLED = 'M5 2h14v20l-7-5.2L5 22z';

/** Bookmark ribbon, outline — the bucket, not a specific collection. viewBox="0 0 24 24". */
export const RIBBON_OUTLINE = 'M6 3h12v18l-6-4.4L6 21z';

/**
 * Outline die — the Untagged bucket is a placeholder, not an identity.
 * Three strokes, drawn at viewBox="0 0 640 640" with stroke-width="40".
 */
export const DIE_OUTLINE = [
  'M320 76 L548 206 L548 434 L320 564 L92 434 L92 206 Z',
  'M92 206 L320 336 L548 206',
  'M320 336 L320 564',
] as const;
