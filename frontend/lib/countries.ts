/** Country name → emoji flag mapping for European countries */
export const COUNTRY_FLAGS: Record<string, string> = {
  "United Kingdom": "\u{1F1EC}\u{1F1E7}",
  UK: "\u{1F1EC}\u{1F1E7}",
  France: "\u{1F1EB}\u{1F1F7}",
  Spain: "\u{1F1EA}\u{1F1F8}",
  Italy: "\u{1F1EE}\u{1F1F9}",
  Germany: "\u{1F1E9}\u{1F1EA}",
  Netherlands: "\u{1F1F3}\u{1F1F1}",
  Belgium: "\u{1F1E7}\u{1F1EA}",
  Luxembourg: "\u{1F1F1}\u{1F1FA}",
  Switzerland: "\u{1F1E8}\u{1F1ED}",
  Austria: "\u{1F1E6}\u{1F1F9}",
  Portugal: "\u{1F1F5}\u{1F1F9}",
  Greece: "\u{1F1EC}\u{1F1F7}",
  Ireland: "\u{1F1EE}\u{1F1EA}",
  Denmark: "\u{1F1E9}\u{1F1F0}",
  Sweden: "\u{1F1F8}\u{1F1EA}",
  Norway: "\u{1F1F3}\u{1F1F4}",
  Finland: "\u{1F1EB}\u{1F1EE}",
  Iceland: "\u{1F1EE}\u{1F1F8}",
  "Czech Republic": "\u{1F1E8}\u{1F1FF}",
  Czechia: "\u{1F1E8}\u{1F1FF}",
  Poland: "\u{1F1F5}\u{1F1F1}",
  Hungary: "\u{1F1ED}\u{1F1FA}",
  Croatia: "\u{1F1ED}\u{1F1F7}",
  Slovenia: "\u{1F1F8}\u{1F1EE}",
  Slovakia: "\u{1F1F8}\u{1F1F0}",
  Romania: "\u{1F1F7}\u{1F1F4}",
  Bulgaria: "\u{1F1E7}\u{1F1EC}",
  Estonia: "\u{1F1EA}\u{1F1EA}",
  Latvia: "\u{1F1F1}\u{1F1FB}",
  Lithuania: "\u{1F1F1}\u{1F1F9}",
};

export function getFlagEmoji(country: string): string {
  return COUNTRY_FLAGS[country] ?? "\u{1F30D}";
}
