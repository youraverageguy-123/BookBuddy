import { afterEach, describe, expect, it, vi } from "vitest";
import { defaultPresentation } from "../../store/readerStore";
import { applyReaderDocumentStyles, buildReaderDocumentStyles, preparePublisherImages, reinforcePublisherInitials } from "./readerDocumentStyles";

describe("EPUB reader document styles", () => {
  afterEach(() => { document.head.innerHTML = ""; document.body.innerHTML = ""; document.documentElement.removeAttribute("style"); document.body.removeAttribute("style"); vi.unstubAllGlobals(); });
  it("preserves publisher drop caps and first-letter rules when publisher fonts are enabled", async () => {
    document.head.innerHTML = '<style id="publisher">span.dropcaps{float:left;font-size:3em}p.opening::first-letter{background:#c6a15b}</style>';
    document.body.innerHTML = '<p class="opening"><span class="dropcaps">T</span>he beginning.</p>';
    const css = buildReaderDocumentStyles({ ...defaultPresentation, usePublisherFonts: true, fontFamily: "Literata, serif" }, { paper: "#fff", ink: "#111" });

    applyReaderDocumentStyles(document, css, { paper: "#fff", ink: "#111" });
    await reinforcePublisherInitials(document, true);

    expect(document.querySelector("#publisher")?.textContent).toContain("span.dropcaps");
    expect(document.querySelector("#publisher")?.textContent).toContain("::first-letter");
    expect(css).not.toContain("font-family");
    expect(css).toContain("font-size: 19px !important");
    expect(css).toContain("line-height: 1.65 !important");
    expect(css).toContain("margin-block-end: 0.8em !important");
    expect(css).not.toContain("max-width: 760px");
    expect(css).not.toContain("img, svg, video, figure");
    expect(document.querySelector("span.dropcaps")?.textContent).toBe("T");
    expect(document.querySelector("#publisher")?.textContent).toBe("span.dropcaps{float:left;font-size:3em}p.opening::first-letter{background:#c6a15b}");
    expect(document.querySelector("style[data-bookbuddy-publisher-initials]")).toBeNull();
  });

  it("only scales publisher media when the reader explicitly requests it", () => {
    const untouched = buildReaderDocumentStyles({ ...defaultPresentation, imageScale: 1, fontFamily: "Literata, serif" }, { paper: "#fff", ink: "#111" });
    const scaled = buildReaderDocumentStyles({ ...defaultPresentation, imageScale: 0.75, fontFamily: "Literata, serif" }, { paper: "#fff", ink: "#111" });

    expect(untouched).toContain("max-width: 100%");
    expect(untouched).toContain("object-fit: contain");
    expect(scaled).toContain("max-width: min(100%, 75%) !important");
  });

  it("applies BookBuddy typography only when publisher fonts are disabled", () => {
    const css = buildReaderDocumentStyles({ ...defaultPresentation, usePublisherFonts: false, fontFamily: "Atkinson Hyperlegible, sans-serif", paragraphSpacing: 1.2 }, { paper: "#000", ink: "#fff" });

    expect(css).toContain('font-family: Atkinson Hyperlegible, sans-serif !important;');
    expect(css).not.toContain("body, body *");
    expect(css).toContain("margin-block-end: 1.2em !important");
    expect(css).not.toContain("overflow-x: hidden !important");
    expect(css).not.toContain("padding-inline: 4% !important");
  });

  it("keeps publisher structure while every named reader control has authoritative CSS", () => {
    const css = buildReaderDocumentStyles({
      ...defaultPresentation,
      usePublisherFonts: true,
      fontSize: 27,
      lineSpacing: 2,
      paragraphSpacing: 1.4,
      justification: "justify",
      hyphenation: true,
      fontFamily: "Publisher font",
    }, { paper: "#fff", ink: "#111" });

    expect(css).not.toContain("font-family: Publisher font");
    expect(css).toContain("font-size: 27px !important");
    expect(css).toContain("line-height: 2 !important");
    expect(css).toContain("margin-block-end: 1.4em !important");
    expect(css).toContain("text-align: justify !important");
    expect(css).toContain("hyphens: auto !important");
    expect(css).not.toContain("font-style:");
    expect(css).not.toContain("text-indent:");
    expect(css).not.toContain("font-weight:");
  });

  it("does not clip epub.js horizontal columns in paginated mode", () => {
    const paginated = buildReaderDocumentStyles({ ...defaultPresentation, fontFamily: "Literata, serif" }, { paper: "#fff", ink: "#111" }, "paginated");
    const scrolled = buildReaderDocumentStyles({ ...defaultPresentation, fontFamily: "Literata, serif" }, { paper: "#fff", ink: "#111" }, "scrolled");

    expect(paginated).not.toContain("overflow-x: hidden !important");
    expect(scrolled).toContain("overflow-x: hidden !important");
  });

  it("does not rewrite publisher initial geometry or cascade", async () => {
    document.head.innerHTML = '<style>.opening::first-letter{float:left;font-family:"Publisher Initial";font-size:4em;line-height:.7}</style>';
    document.body.innerHTML = '<p class="opening">Once upon a time.</p>';

    await reinforcePublisherInitials(document, true);

    expect(document.querySelector("style")?.textContent).toBe('.opening::first-letter{float:left;font-family:"Publisher Initial";font-size:4em;line-height:.7}');
    expect(document.querySelector("style[data-bookbuddy-publisher-initials]")).toBeNull();
  });

  it("does not invent chapter initials and preserves intrinsic image geometry", async () => {
    document.body.innerHTML = '<h2>Chapter One</h2><p>Once upon a time the opening paragraph begins.</p><img width="2400" height="3600" src="cover.jpg">';

    await reinforcePublisherInitials(document, true);
    preparePublisherImages(document);

    expect(document.querySelector("p")?.classList.contains("bookbuddy-fallback-initial")).toBe(false);
    expect(document.querySelector("style[data-bookbuddy-publisher-initials]")).toBeNull();
    expect(document.querySelector("img")?.getAttribute("width")).toBe("2400");
    expect(document.querySelector("img")?.getAttribute("height")).toBe("3600");
    expect((document.querySelector("img") as HTMLImageElement).decoding).toBe("async");
  });

  it("recovers a linked publisher stylesheet after a reported load failure", async () => {
    document.head.innerHTML = '<link rel="stylesheet" href="https://bookbuddy.invalid/publisher.css" data-bookbuddy-load-failed="true">';
    vi.stubGlobal("fetch", vi.fn(async () => new Response('h1{font-family:"Publisher Heading"}.opening:first-letter{float:left;font-size:3.2em;line-height:.7;font-family:"Publisher Initial"}', { status: 200 })));

    await reinforcePublisherInitials(document, true);

    const recovered = document.querySelector("style[data-bookbuddy-recovered-publisher-styles]")?.textContent ?? "";
    expect(recovered).toContain(".opening:first-letter");
    expect(recovered).toContain("font-size:3.2em");
    expect(recovered).toContain('h1{font-family:"Publisher Heading"}');
  });

  it("decodes a CSP-blocked data stylesheet even when its error event was missed", async () => {
    const publisherCss = '.para-cn-chap-pg{text-align:center;border-bottom:1px solid}.para-cst{text-align:center;font-style:italic}.pcalibre:first-letter{float:left;font-size:3.2em}.fv-smallcaps{font-variant:small-caps}';
    document.head.innerHTML = `<link rel="stylesheet" href="data:text/css;base64,${btoa(publisherCss)}">`;
    vi.stubGlobal("fetch", vi.fn(() => { throw new Error("data fetch must not be needed"); }));

    await reinforcePublisherInitials(document, true);

    const recovered = document.querySelector("style[data-bookbuddy-recovered-publisher-styles]")?.textContent ?? "";
    expect(recovered).toBe(publisherCss);
    expect(recovered).toContain(".pcalibre:first-letter");
    expect(recovered).toContain(".fv-smallcaps");
  });

  it("forces the active palette onto the EPUB page roots even over inline publisher colors", () => {
    document.documentElement.style.cssText = "background:white!important;color:black!important";
    document.body.style.cssText = "background:white!important;color:black!important";

    applyReaderDocumentStyles(document, "body{}", { paper: "#000000", ink: "#ffffff" });

    expect(document.documentElement.style.getPropertyValue("background-color")).toBe("rgb(0, 0, 0)");
    expect(document.documentElement.style.getPropertyPriority("background-color")).toBe("important");
    expect(document.body.style.getPropertyValue("color")).toBe("rgb(255, 255, 255)");
  });

  it("forces live typography controls and keeps recovered publisher CSS before them", async () => {
    const publisherCss = '.opening:first-letter{float:left;font-size:4em;line-height:.7}p{line-height:1!important}';
    document.head.innerHTML = `<link rel="stylesheet" href="data:text/css;base64,${btoa(publisherCss)}">`;
    document.body.innerHTML = '<p class="opening"><span>T</span>he beginning.</p>';
    const settings = { ...defaultPresentation, usePublisherFonts:false, fontFamily:'"Segoe Print", cursive', fontSize:25, lineSpacing:2.1 };
    const css = buildReaderDocumentStyles(settings,{paper:"#fff",ink:"#111"});

    applyReaderDocumentStyles(document,css,{paper:"#fff",ink:"#111"},"paginated",settings);
    await reinforcePublisherInitials(document,true);

    const paragraph=document.querySelector("p") as HTMLElement;
    const readerStyle=document.querySelector("style[data-bookbuddy-reader-styles]") as HTMLStyleElement;
    const recovered=document.querySelector("style[data-bookbuddy-recovered-publisher-styles]") as HTMLStyleElement;
    expect(paragraph.style.getPropertyValue("font-family")).toContain("Segoe Print");
    expect(paragraph.style.getPropertyPriority("font-family")).toBe("important");
    expect(paragraph.style.getPropertyValue("line-height")).toBe("2.1");
    expect(recovered.compareDocumentPosition(readerStyle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(recovered.textContent).toContain("float:left");
  });
});
