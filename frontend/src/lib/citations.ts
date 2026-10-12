/**
 * Some models (e.g. gpt-oss) cite as 【1†L1-L4】 instead of the requested [1].
 * Show them the same way; the saved text keeps whatever the model wrote.
 */
export function normalizeCitations(text: string): string {
  return text.replace(/【(\d+)(?:†[^】]*)?】/g, '[$1]')
}
