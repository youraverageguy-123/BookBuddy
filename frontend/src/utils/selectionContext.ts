export interface SelectionContextWindow {
  paragraph: string; sentence: string; previousSentence: string; nextSentence: string;
  sentenceSelectionStart: number; sentenceSelectionEnd: number;
}

export const buildSelectionContext = (paragraphText: string, selectedText: string, approximateStart: number): SelectionContextWindow => {
  const rawStart = Math.max(0, Math.min(approximateStart, paragraphText.length));
  const cropStart = Math.max(0, Math.min(rawStart - 1_500, Math.max(0, paragraphText.length - 4_000)));
  const paragraph = paragraphText.slice(cropStart, cropStart + 4_000);
  const localApproximation = rawStart - cropStart;
  const exactAtApproximation = paragraph.slice(localApproximation, localApproximation + selectedText.length) === selectedText;
  const selectionStart = exactAtApproximation ? localApproximation : (() => {
    const escaped = selectedText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const occurrences = Array.from(paragraph.matchAll(new RegExp(escaped, "g")), (match) => match.index);
    return occurrences.sort((a, b) => Math.abs(a - localApproximation) - Math.abs(b - localApproximation))[0] ?? Math.max(0, localApproximation);
  })();
  const spans = Array.from(paragraph.matchAll(/[^.!?]+(?:[.!?]+|$)/g), (match) => ({ text: match[0].trim(), start: match.index + (match[0].length - match[0].trimStart().length), end: match.index + match[0].length }));
  const foundIndex = spans.findIndex((span) => selectionStart >= span.start && selectionStart <= span.end);
  const index = foundIndex >= 0 ? foundIndex : 0;
  const selectedSpan = spans[index] ?? { text: paragraph, start: 0, end: paragraph.length };
  return {
    paragraph,
    sentence: selectedSpan.text,
    previousSentence: spans[index - 1]?.text ?? "",
    nextSentence: spans[index + 1]?.text ?? "",
    sentenceSelectionStart: Math.max(0, selectionStart - selectedSpan.start),
    sentenceSelectionEnd: Math.max(0, selectionStart - selectedSpan.start) + selectedText.length,
  };
};
