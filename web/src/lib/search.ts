/** Space-separated terms, every term must appear somewhere across the given
 * fields (case-insensitive) - lets "acme engineer" narrow down by company
 * AND title at once instead of only matching one field per query. */
export function matchesSearch(query: string, fields: (string | null | undefined)[]): boolean {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const haystack = fields.filter(Boolean).join(" \u0000 ").toLowerCase();
  return terms.every((t) => haystack.includes(t));
}
