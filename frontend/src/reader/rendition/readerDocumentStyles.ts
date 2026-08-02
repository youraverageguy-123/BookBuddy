import type { ReaderPresentationSettings } from "../../store/readerStore";

export interface ReaderPalette {
  paper: string;
  ink: string;
}

export type ReaderDocumentFlow = "paginated" | "scrolled";

function ensureHead(document: Document): HTMLHeadElement | null {
  if (document.head) return document.head;
  const root = document.documentElement;
  if (!root) return null;
  const head = document.createElement("head");
  root.insertBefore(head, document.body ?? root.firstChild);
  return head;
}

export function buildReaderDocumentStyles(settings: ReaderPresentationSettings & { fontFamily: string }, palette: ReaderPalette, flow: ReaderDocumentFlow = "paginated"): string {
  const fontOverride = settings.usePublisherFonts ? "" : `
body,
body :where(p, div, span, li, blockquote, td, th, dd, dt, h1, h2, h3, h4, h5, h6, figcaption) {
  font-family: ${settings.fontFamily} !important;
}
`;

  // EPUB structure stays publisher-owned. Reader controls override only the
  // exact typographic property they name, so headings, drop caps, indents,
  // emphasis, spacing classes, and image placement continue to come from the
  // book while the selected control responds immediately.
  const readerTuning = `
body {
  font-size: ${settings.fontSize}px !important;
}
body, p, li, blockquote {
  line-height: ${settings.lineSpacing} !important;
  hyphens: ${settings.hyphenation ? "auto" : "none"} !important;
  -webkit-hyphens: ${settings.hyphenation ? "auto" : "none"} !important;
}
p {
  margin-block-end: ${settings.paragraphSpacing}em !important;
  text-align: ${settings.justification} !important;
}
`;

  const scaledMedia = settings.imageScale < 0.999 ? `
img, svg, video {
  max-width: min(100%, ${Math.round(settings.imageScale * 100)}%) !important;
  max-height: calc(100vh * ${settings.imageScale}) !important;
}
` : "";

  const scrollingSafety = flow === "scrolled" ? "overflow-x: hidden !important;" : "";
  const readerMargins = settings.marginPercent !== 4 ? `padding-inline: ${settings.marginPercent}% !important;` : "";
  return `
html, body {
  ${scrollingSafety}
  background: ${palette.paper} !important;
  color: ${palette.ink} !important;
}
body {
  box-sizing: border-box !important;
  ${readerMargins}
}
a { color: inherit; }
script, iframe, object, embed, form { display: none !important; }
img, svg, video {
  max-width: 100%;
  max-height: calc(100vh - 2px);
  height: auto;
  object-fit: contain;
  image-rendering: auto;
  break-inside: avoid;
}
img, svg { cursor: zoom-in; }
figure { max-width: 100%; break-inside: avoid; }
.bookbuddy-raster-image {
  max-width: min(100%, var(--bookbuddy-intrinsic-width, 100%));
}
${scaledMedia}
${fontOverride}
${readerTuning}`.trim();
}

export function applyReaderDocumentStyles(document: Document, css: string, palette: ReaderPalette, flow: ReaderDocumentFlow = "paginated", settings?: ReaderPresentationSettings & { fontFamily: string }): void {
  const head = ensureHead(document);
  let style = head?.querySelector<HTMLStyleElement>("style[data-bookbuddy-reader-styles]");
  if (!style) {
    style = document.createElement("style");
    style.dataset.bookbuddyReaderStyles = "active";
    head?.appendChild(style);
  }
  style.textContent = css;
  // Author styles in real EPUBs frequently use highly-specific !important
  // declarations. Apply the controls directly as well so a live reader
  // change always wins without flattening any structural publisher rules.
  if (settings) {
    const previouslyTouched = document.querySelectorAll<HTMLElement>("[data-bookbuddy-typography]");
    previouslyTouched.forEach((element) => {
      element.style.removeProperty("font-family");
      element.style.removeProperty("font-size");
      element.style.removeProperty("line-height");
      element.style.removeProperty("hyphens");
      element.style.removeProperty("-webkit-hyphens");
      element.style.removeProperty("margin-block-end");
      element.style.removeProperty("text-align");
      delete element.dataset.bookbuddyTypography;
    });
    const textElements = document.querySelectorAll<HTMLElement>("body, body p, body div, body span, body li, body blockquote, body td, body th, body dd, body dt, body h1, body h2, body h3, body h4, body h5, body h6, body figcaption");
    textElements.forEach((element) => {
      element.dataset.bookbuddyTypography = "active";
      if (!settings.usePublisherFonts) element.style.setProperty("font-family", settings.fontFamily, "important");
    });
    document.body?.style.setProperty("font-size", `${settings.fontSize}px`, "important");
    document.querySelectorAll<HTMLElement>("body, body p, body li, body blockquote").forEach((element) => {
      element.dataset.bookbuddyTypography = "active";
      element.style.setProperty("line-height", String(settings.lineSpacing), "important");
      element.style.setProperty("hyphens", settings.hyphenation ? "auto" : "none", "important");
      element.style.setProperty("-webkit-hyphens", settings.hyphenation ? "auto" : "none", "important");
    });
    document.querySelectorAll<HTMLElement>("body p").forEach((element) => {
      element.style.setProperty("margin-block-end", `${settings.paragraphSpacing}em`, "important");
      element.style.setProperty("text-align", settings.justification, "important");
    });
  }
  for (const element of [document.documentElement, document.body]) {
    if (!element) continue;
    element.style.setProperty("background", palette.paper, "important");
    element.style.setProperty("background-color", palette.paper, "important");
    element.style.setProperty("color", palette.ink, "important");
    if (flow === "scrolled") element.style.setProperty("overflow-x", "hidden", "important");
    else element.style.removeProperty("overflow-x");
  }
}

const publisherRuleRequests = new WeakMap<Document, number>();

function decodeCssDataUrl(url: string): string | null {
  if (!url.toLowerCase().startsWith("data:")) return null;
  const comma = url.indexOf(",");
  if (comma < 0) return null;
  const metadata = url.slice(5, comma);
  const payload = url.slice(comma + 1);
  try {
    if (/;base64(?:;|$)/i.test(metadata)) {
      const binary = atob(payload);
      const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
      return new TextDecoder().decode(bytes);
    }
    return decodeURIComponent(payload);
  } catch {
    return null;
  }
}

function rebaseCssUrls(css: string, stylesheetUrl: string): string {
  if (stylesheetUrl.toLowerCase().startsWith("data:")) return css;
  return css.replace(/url\(\s*(["']?)([^"')]+)\1\s*\)/gi, (match, quote: string, value: string) => {
    const reference = value.trim();
    if (!reference || reference.startsWith("#") || /^(?:data|blob|https?|file|javascript):/i.test(reference)) return match;
    try {
      return `url(${quote}${new URL(reference, stylesheetUrl).href}${quote})`;
    } catch {
      return match;
    }
  });
}

async function readLinkedStylesheet(link: HTMLLinkElement, fetcher?: typeof fetch): Promise<string | null> {
  const inlineData = decodeCssDataUrl(link.href);
  if (inlineData !== null) return inlineData;
  if (!fetcher) return null;
  try {
    const response = await fetcher(link.href);
    return response.ok ? rebaseCssUrls(await response.text(), link.href) : null;
  } catch {
    return null;
  }
}

/** Recover publisher stylesheets that WebView2 blocked before listeners attached. */
export async function reinforcePublisherInitials(document: Document, enabled: boolean): Promise<void> {
  const head = ensureHead(document);
  head?.querySelector("style[data-bookbuddy-recovered-publisher-styles]")?.remove();
  if (!enabled || !head) return;
  const request = (publisherRuleRequests.get(document) ?? 0) + 1;
  publisherRuleRequests.set(document, request);
  const fetcher = document.defaultView?.fetch?.bind(document.defaultView) ?? globalThis.fetch;
  const unresolvedLinks = Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel~="stylesheet"][href]'))
    // epub.js embeds archived CSS as data URLs. WebView2 may expose a sheet
    // object for them even though the release CSP has blocked all its rules.
    .filter((link) => link.href.toLowerCase().startsWith("data:") || link.dataset.bookbuddyLoadFailed === "true" || !link.sheet);
  if (!unresolvedLinks.length) return;
  const recoveredStyles = (await Promise.all(unresolvedLinks.map((link) => readLinkedStylesheet(link, fetcher))))
    .filter((css): css is string => Boolean(css));
  if (publisherRuleRequests.get(document) !== request) return;
  if (!recoveredStyles.length) return;
  const recovered = document.createElement("style");
  recovered.dataset.bookbuddyRecoveredPublisherStyles = "active";
  recovered.textContent = recoveredStyles.join("\n");
  const readerStyles = head.querySelector("style[data-bookbuddy-reader-styles]");
  head.insertBefore(recovered, readerStyles);
}

export function preparePublisherImages(document: Document): void {
  document.querySelectorAll<HTMLImageElement>("img").forEach((image) => {
    image.decoding = "async";
    image.loading = "eager";
    const constrainToIntrinsicSize = () => {
      if (!image.naturalWidth) return;
      image.classList.add("bookbuddy-raster-image");
      const scale = Math.max(1, document.defaultView?.devicePixelRatio ?? 1);
      image.style.setProperty("--bookbuddy-intrinsic-width", `${Math.ceil(image.naturalWidth / scale)}px`);
    };
    if (image.complete) constrainToIntrinsicSize();
    else image.addEventListener("load", constrainToIntrinsicSize, { once: true });
  });
  document.querySelectorAll<HTMLLinkElement>('link[rel~="stylesheet"][href]').forEach((link) => {
    if (link.dataset.bookbuddyLoadObserved) return;
    link.dataset.bookbuddyLoadObserved = "true";
    link.addEventListener("error", () => {
      link.dataset.bookbuddyLoadFailed = "true";
      void reinforcePublisherInitials(document, true);
    }, { once: true });
  });
}
