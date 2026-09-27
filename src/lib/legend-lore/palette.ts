// Manuscript-pigment palette for user-assigned collection colors.
// Collections only — game systems are monochrome (shield + parchment ink).
// All hues share oklch L 0.64, C 0.10 so no color shouts over another on
// the dark shell. Hue gaps ≥35° keep neighbors distinguishable. Reserved
// UI hues are deliberately excluded so user colors can't impersonate
// semantics: mode purple (~300°), parchment/brass, pilot-lamp amber,
// bright danger red.
export interface Pigment {
  name: string;
  hex: string;
}

export const PIGMENTS: Pigment[] = [
  { name: 'Madder',    hex: '#c2736d' }, // oklch(0.64 0.10 25)
  { name: 'Ember',     hex: '#bb7b4e' }, // oklch(0.64 0.10 55)
  { name: 'Gilt',      hex: '#9f8b3e' }, // oklch(0.64 0.10 95)
  { name: 'Moss',      hex: '#6b9b60' }, // oklch(0.64 0.10 140)
  { name: 'Verdigris', hex: '#2fa094' }, // oklch(0.64 0.10 185)
  { name: 'Woad',      hex: '#5b90c7' }, // oklch(0.64 0.10 250)
  { name: 'Plum',      hex: '#b5739f' }, // oklch(0.64 0.10 340)
];

export const PALETTE: string[] = PIGMENTS.map((p) => p.hex);
