// Sorcerer's-cabinet palette for user-assigned collection colors: minerals
// and dyes off a sorcerer's shelf. Collections only — game systems are
// monochrome (shield + parchment ink).
// The warm hues belong to the interface — vermilion danger/mute, pilot-lamp
// amber, parchment/brass — and so does mode purple (~300°); every pigment
// sits ≥ ΔE 10 (OKLab ×100) from them so user colors can't impersonate
// semantics. Lightness varies (0.62–0.78) rather than being shared: at one
// shared L, red/green pairs collapse for deuteranopes. Closest pair is
// ΔE 8 (Malachite/Verdigris), 6 under deuteranopia or protanopia. L stays
// ≥ 0.61 so --text-inverse clears 4.5:1 on a selected index cell's fill.
// Collections store the hex itself: when a pigment changes, remap the old
// hex in the sidecar's _migrate_collection_record.
export interface Pigment {
  name: string;
  hex: string;
}

export const PIGMENTS: Pigment[] = [
  { name: 'Madder',    hex: '#d07c87' }, // oklch(0.68 0.105 12)
  { name: 'Arsenic',   hex: '#abc279' }, // oklch(0.78 0.10 123)
  { name: 'Malachite', hex: '#4e9766' }, // oklch(0.615 0.105 153)
  { name: 'Verdigris', hex: '#43a49f' }, // oklch(0.66 0.09 191)
  { name: 'Woad',      hex: '#6b9ad0' }, // oklch(0.675 0.095 252)
  { name: 'Murex',     hex: '#dba2c3' }, // oklch(0.775 0.08 343)
];

export const PALETTE: string[] = PIGMENTS.map((p) => p.hex);
