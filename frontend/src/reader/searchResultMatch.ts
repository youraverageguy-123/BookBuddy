export interface EpubSearchMatch {
  cfi: string;
  excerpt?: string;
}

export interface DocumentSearchMatch {
  range: Range;
  excerpt: string;
}

const words = (value: string): string[] => value
  .replace(/<\/?mark>/gi, " ")
  .replace(/…|\.\.\./g, " ")
  .toLocaleLowerCase()
  .match(/[\p{L}\p{N}'’-]+/gu) ?? [];

export function selectSearchResultMatch(matches: EpubSearchMatch[], resultExcerpt: string): EpubSearchMatch | undefined {
  if (matches.length <= 1) return matches[0];
  const resultWords = new Set(words(resultExcerpt));
  if (!resultWords.size) return matches[0];
  return matches.reduce((best, candidate) => {
    const score = words(candidate.excerpt ?? "").reduce((total, word) => total + (resultWords.has(word) ? 1 : 0), 0);
    return score > best.score ? { match: candidate, score } : best;
  }, { match: matches[0], score: -1 }).match;
}

export function findDocumentSearchMatches(document: Document, query: string): DocumentSearchMatch[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle || !document.body) return [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => node.parentElement?.closest("script,style,noscript") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  const nodes: Array<{ node: Text; start: number; end: number }> = [];
  let text = "";
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const value = node.textContent ?? "";
    const start = text.length;
    text += value;
    nodes.push({ node: node as Text, start, end: text.length });
  }
  const lowered = text.toLocaleLowerCase();
  const matches: DocumentSearchMatch[] = [];
  for (let index = lowered.indexOf(needle); index >= 0; index = lowered.indexOf(needle, index + Math.max(1, needle.length))) {
    const end = index + needle.length;
    const startNode = nodes.find((item) => index >= item.start && index < item.end);
    const endNode = [...nodes].reverse().find((item) => end > item.start && end <= item.end);
    if (!startNode || !endNode) continue;
    const range = document.createRange();
    range.setStart(startNode.node, index - startNode.start);
    range.setEnd(endNode.node, end - endNode.start);
    matches.push({ range, excerpt: text.slice(Math.max(0, index - 90), Math.min(text.length, end + 90)) });
  }
  return matches;
}

export function selectDocumentSearchMatch(matches: DocumentSearchMatch[], resultExcerpt: string): DocumentSearchMatch | undefined {
  return selectSearchResultMatch(matches.map((match, index) => ({ cfi: String(index), excerpt: match.excerpt })), resultExcerpt)
    ? matches[Number(selectSearchResultMatch(matches.map((match, index) => ({ cfi: String(index), excerpt: match.excerpt })), resultExcerpt)?.cfi)]
    : undefined;
}
