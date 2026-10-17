// Sorcerer's-cabinet palette for user-assigned collection colors: minerals
// and dyes off a sorcerer's shelf. Collections only — game systems are
// monochrome (shield + parchment ink).
// The warm hues belong to the interface — vermilion danger/mute, pilot-lamp
// amber, parchment/brass — and so does mode purple (~300°); every pigment
// sits ≥ ΔE 10 (OKLab ×100) from them so user colors can't impersonate
// semantics. So the red is a crimson, not a scarlet, and the orange, ochre
// and violet clear their neighbors by running lighter. Lightness varies
// (0.625–0.835) rather than being shared: at one shared L, hue pairs collapse
// for deuteranopes. Closest pair is ΔE 7.6 (Kermes/Murex), 6.1 under
// deuteranopia, 5.9 under protanopia. L stays ≥ 0.625 so --text-inverse
// clears 4.5:1 on a selected index cell's fill.
// Collections store the hex itself: when a pigment changes, remap the old
// hex in the sidecar's _migrate_collection_record.
export interface Pigment {
  name: string;
  hex: string;
}

export const PIGMENTS: Pigment[] = [
  { name: 'Kermes',    hex: '#c3638d' }, // oklch(0.625 0.13 354)
  { name: 'Madder',    hex: '#eb98a2' }, // oklch(0.765 0.10 12)
  { name: 'Realgar',   hex: '#f29349' }, // oklch(0.75 0.145 56)
  { name: 'Ochre',     hex: '#e6c667' }, // oklch(0.835 0.12 91)
  { name: 'Malachite', hex: '#66965c' }, // oklch(0.625 0.10 140)
  { name: 'Azurite',   hex: '#8dceee' }, // oklch(0.82 0.08 230)
  { name: 'Lapis',     hex: '#478bdb' }, // oklch(0.63 0.14 254)
  { name: 'Orchil',    hex: '#c29ce9' }, // oklch(0.755 0.115 306)
  { name: 'Murex',     hex: '#d379b7' }, // oklch(0.695 0.135 340)
];

export const PALETTE: string[] = PIGMENTS.map((p) => p.hex);
