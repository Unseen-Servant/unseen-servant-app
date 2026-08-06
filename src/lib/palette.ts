// Manuscript-pigment palette for user-assigned collection/system colors.
// All hues share oklch L 0.64, C 0.10 so no color shouts over another on
// the dark shell. Hue gaps ≥35° keep neighbors distinguishable. Reserved
// UI hues are deliberately excluded so user colors can't impersonate
// semantics: mode purple (~300°), parchment/brass, pilot-lamp amber,
// bright danger red.
export const PALETTE: string[] = [
  '#c2736d', // Madder    oklch(0.64 0.10 25)
  '#bb7b4e', // Ember     oklch(0.64 0.10 55)
  '#9f8b3e', // Gilt      oklch(0.64 0.10 95)
  '#6b9b60', // Moss      oklch(0.64 0.10 140)
  '#2fa094', // Verdigris oklch(0.64 0.10 185)
  '#5b90c7', // Woad      oklch(0.64 0.10 250)
  '#b5739f', // Plum      oklch(0.64 0.10 340)
];
