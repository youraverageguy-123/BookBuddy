const VIEWPORT_GUTTER = 12;
const READER_CHROME_TOP = 62;
const READER_CHROME_BOTTOM = 44;
const SELECTION_GAP = 10;

export function selectionToolbarPlacement(x: number, y: number, width: number, height: number, viewportWidth: number, viewportHeight: number) {
  const maximumLeft = Math.max(VIEWPORT_GUTTER, viewportWidth - width - VIEWPORT_GUTTER);
  const left = Math.min(Math.max(x - width / 2, VIEWPORT_GUTTER), maximumLeft);
  const maximumTop = Math.max(READER_CHROME_TOP, viewportHeight - READER_CHROME_BOTTOM - height);
  const preferredTop = y - height - SELECTION_GAP;
  const alternateTop = y + SELECTION_GAP;
  const top = Math.min(Math.max(preferredTop >= READER_CHROME_TOP ? preferredTop : alternateTop, READER_CHROME_TOP), maximumTop);
  return { left, top };
}
