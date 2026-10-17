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
 * Font Awesome "circle" (solid) and "circle" (regular, a ring). The record-arm
 * glyph: the ring while a collection is disarmed, the solid circle once armed.
 * Drawn with viewBox="64 64 512 512" — the vendored 640 box cropped to the
 * circle, so the rendered size is the glyph's size.
 * Sources: ./icons/circle-solid-full.svg, ./icons/circle-regular-full.svg
 */
export const CIRCLE =
  'M64 320C64 178.6 178.6 64 320 64C461.4 64 576 178.6 576 320C576 461.4 461.4 576 320 576C178.6 576 64 461.4 64 320z';

export const CIRCLE_RING =
  'M528 320C528 205.1 434.9 112 320 112C205.1 112 112 205.1 112 320C112 434.9 205.1 528 320 528C434.9 528 528 434.9 528 320zM64 320C64 178.6 178.6 64 320 64C461.4 64 576 178.6 576 320C576 461.4 461.4 576 320 576C178.6 576 64 461.4 64 320z';

/**
 * Font Awesome "play". The transport's launch key: a collection playing in
 * Legend Lore, a note or beat launched in Command. viewBox="0 0 640 640".
 * Source: ./icons/play-solid-full.svg
 */
export const PLAY =
  'M187.2 100.9C174.8 94.1 159.8 94.4 147.6 101.6C135.4 108.8 128 121.9 128 136L128 504C128 518.1 135.5 531.2 147.6 538.4C159.7 545.6 174.8 545.9 187.2 539.1L523.2 355.1C536 348.1 544 334.6 544 320C544 305.4 536 291.9 523.2 284.9L187.2 100.9z';

/**
 * Gem, hollow — always stroked, never filled (stroke-width 2.2). Font Awesome
 * "gem" (regular) traced along the centre of its bands, so it takes a stroke
 * and a dash. A collection's gem is stroked in its pigment; one without a
 * pigment, and the "in a collection" bucket, in tertiary grey. The header's
 * collections key draws the solid gem.
 * viewBox="0 0 24 24". Source: ./icons/gem-regular-full.svg
 *
 * GEM_OUTLINE is its silhouette without the facets: Loose dashes it, since
 * dashes run across the facets and turn the whole gem to noise. GEM is built
 * on it so the two can't drift.
 */
export const GEM_OUTLINE = 'M7.5 4.5h9l4 5.5-8.5 9.5L3.5 10z';

export const GEM = `${GEM_OUTLINE}M3.5 10h17M7.5 4.5 12 10l4.5-5.5`;

/**
 * Heater shield — a game system. Always stroked, never filled: systems are
 * monochrome and carry no colour of their own. The Untagged bucket draws the
 * same shield dashed (a placeholder, not an identity), as Loose does with the
 * collection gem. viewBox="0 0 24 24", stroke-width="2.2".
 */
export const SHIELD = 'M12 3l7 2.5V11c0 5-3.3 8.2-7 10-3.7-1.8-7-5-7-10V5.5z';

/**
 * The Unseen Servant mark: the visible path of static/logo.svg, drawn inline
 * so it takes the text colour. MARK_VIEWBOX crops the logo's 1024 box to its
 * ink. Drawn by the launch splash and the rack bar.
 */
export const MARK_VIEWBOX = '165 38 685 960';

export const MARK =
  'm 531.48251,996.79425 c 0,-5.71119 80.68699,-261.64303 109.0722,-345.96722 6.0315,-17.91785 12.17387,-33.7718 13.64974,-35.23102 1.4759,-1.45926 8.97158,-6.53133 16.65711,-11.27128 32.9359,-20.31284 54.16842,-37.98849 67.47142,-56.16879 16.04415,-21.92635 28.9418,-50.48234 35.45033,-78.48854 3.95674,-17.02593 3.36988,-18.27563 -6.92975,-14.75602 -11.52545,3.93853 -212.0373,91.42258 -217.37196,94.84017 -1.13116,0.72468 -2.94191,10.75759 -4.81899,26.70112 -1.65383,14.04712 -8.58032,71.92537 -15.39224,128.61831 -6.81191,56.69293 -14.42215,120.78987 -16.91162,142.4377 -2.48951,21.64777 -4.70877,39.52283 -4.93167,39.72232 -0.22295,0.19947 -1.15122,-5.69449 -2.06281,-13.09769 -30.5443,-248.05411 -40.2297,-324.80923 -41.08136,-325.56271 -1.36618,-1.20865 -154.72578,-68.41341 -189.5819,-83.07797 -30.37703,-12.78012 -34.69824,-14.03535 -36.20704,-10.51716 -3.09314,7.21257 10.41027,48.08159 23.70664,71.74983 18.71388,33.31172 37.76764,51.8621 77.04069,75.00532 9.28187,5.46971 18.28293,10.84278 20.00236,11.94014 3.59039,2.29145 8.91304,16.51555 26.8314,71.70376 35.70962,109.98493 93.67927,298.83806 92.15018,300.20629 -0.30587,0.27368 -12.97652,-26.53685 -28.15704,-59.57898 C 385.07627,784.53947 335.42532,679.18856 327.37515,665.66813 322.54283,657.55205 309.49676,644.31795 271.208,608.69137 l -26.2098,-24.38745 -9.37455,-31.20495 c -5.15599,-17.16271 -11.19157,-36.21454 -13.41243,-42.33738 -2.22083,-6.12284 -15.54974,-32.12212 -29.61972,-57.77625 l -25.58188,-46.6438 -1.1357,-24.29229 c -1.19044,-25.46293 -0.0944,-214.20475 1.48685,-256.05378 l 0.91793,-24.29228 4.16039,32.17087 c 12.21459,94.45047 20.71392,143.5027 27.49954,158.70776 13.76142,30.83628 66.24832,100.75582 91.8508,122.35744 12.70314,10.71809 18.87525,13.58383 101.01526,46.90224 70.35893,28.5397 77.39133,31.17317 80.44448,30.12485 1.40533,-0.48255 2.84378,-2.05367 1.91605,-0.95397 -3.6e-4,4.6e-4 -7.7e-4,8.9e-4 -10e-4,10e-4 -0.9803,1.08152 10.08704,-114.16487 16.7676,-218.7572 10.64568,-166.67129 13.80341,-232.56732 15.48269,-234.129037 0.32356,-0.300936 0.58887,0.880843 0.58956,2.62618 6.9e-4,1.7453 0.64325,9.377691 1.42795,16.960815 2.96013,28.604907 7.61561,93.807712 19.82917,277.719902 7.16743,107.92778 10.68995,154.05248 11.89859,155.80231 0.42269,0.61196 1.47822,1.11268 2.34561,1.11268 4.09913,0 129.08371,-49.77779 157.4724,-62.71677 16.73558,-7.62774 33.09298,-21.95393 55.32485,-48.45472 35.51423,-42.33367 60.90874,-81.69484 66.36391,-102.86321 3.35524,-13.01979 24.3265,-159.5797 24.3265,-170.00844 0,-1.18918 0.66039,-1.79697 1.46749,-1.35064 0.96427,0.53324 1.46752,51.44909 1.46752,148.4749 V 403.0935 l -10.09319,18.03756 c -17.4755,31.23056 -43.69,80.75201 -46.9872,88.76279 -1.74231,4.2331 -7.44344,21.58217 -12.66919,38.55351 -5.22577,16.97131 -10.76407,33.30276 -12.30742,36.29214 -1.75944,3.40796 -16.50401,18.16902 -39.53159,39.57571 l -36.72552,34.14051 -13.52533,28.23157 c -37.75333,78.80308 -87.71024,185.22668 -126.31136,269.08198 -10.49826,22.80593 -19.35928,41.7115 -19.69118,42.01244 -0.33187,0.30092 -0.60342,-0.14358 -0.60342,-0.98779 z';
