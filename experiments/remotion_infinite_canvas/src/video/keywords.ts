export type KeywordItem = {text: string; color: string};

const COLORS = ['#176983', '#d46b08', '#ad2f68'];
const LEXICON = [
  '\u722c\u866b\u7a0b\u5e8f', '\u7f51\u9875\u4fe1\u606f', '\u4e0a\u7f51\u884c\u4e3a', '\u670d\u52a1\u5668',
  '\u53d1\u9001\u8bf7\u6c42', '\u8bf7\u6c42', '\u6d4f\u89c8\u5668', '\u6e90\u4ee3\u7801', 'HTML',
  '\u89e3\u6790', '\u5546\u54c1\u4ef7\u683c', '\u4ef7\u683c', '\u94fe\u63a5\u63d0\u53d6', '\u94fe\u63a5',
  '\u7f51\u7ad9', '\u6570\u636e', '\u4fe1\u606f', '\u4ee3\u7801', '\u5faa\u73af', '\u722c\u53d6',
  '\u8fdd\u89c4', '\u5c01IP', 'IP', '\u5b98\u53f8', '\u6cd5\u5f8b', '\u89c4\u5219', '\u98ce\u9669',
  '\u6548\u7387', '\u81ea\u52a8', '\u76d1\u6d4b', '\u5206\u6790', '\u9690\u79c1',
];
const SORTED_LEXICON = [...new Set(LEXICON)].sort((a, b) => b.length - a.length);

export function extractKeywords(text: string, limit = 3): KeywordItem[] {
  if (!text || limit <= 0) return [];
  const normalized = text.toLocaleLowerCase();
  const counts = new Map<string, {count: number; first: number}>();
  for (const term of SORTED_LEXICON) {
    const needle = term.toLocaleLowerCase();
    let from = 0;
    while (from < normalized.length) {
      const index = normalized.indexOf(needle, from);
      if (index < 0) break;
      const current = counts.get(term) ?? {count: 0, first: index};
      counts.set(term, {count: current.count + 1, first: Math.min(current.first, index)});
      from = index + needle.length;
    }
  }
  const ranked = [...counts.entries()]
    .sort((a, b) => b[1].count - a[1].count || b[0].length - a[0].length || a[1].first - b[1].first)
    .filter(([term], _, all) => !all.some(([other]) => other !== term && other.length > term.length && other.includes(term)))
    .slice(0, limit)
    .sort((a, b) => a[1].first - b[1].first);
  return ranked.map(([term], index) => ({text: term, color: COLORS[index % COLORS.length]}));
}
