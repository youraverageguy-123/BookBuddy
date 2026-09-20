import { describe, expect, it } from "vitest";
import { selectionToolbarPlacement } from "../components/reader/selectionToolbarPlacement";
import readerStyles from "../styles/app.css?raw";
import readerPageSource from "./ReaderPage.tsx?raw";

describe("reader viewport layout", () => {
  it("treats router-decoded session identifiers as final opaque values", () => {
    expect(readerPageSource).toContain("bookName={params.data.book}");
    expect(readerPageSource).toContain("sessionName={params.data.session}");
    expect(readerPageSource).not.toContain("decodeURIComponent(params.data");
  });
  it("pins the optional banner, reading surface, and status bar to stable rows", () => {
    expect(readerStyles).toContain("grid-template-rows:58px auto minmax(0,1fr) 38px");
    expect(readerStyles).toContain(".reader-page.is-fullscreen { grid-template-rows:0 auto minmax(0,1fr) 38px;");
    expect(readerStyles).toContain(".analysis-banner { grid-row:2;");
    expect(readerStyles).toContain(".reading-surface { grid-row:3;");
    expect(readerStyles).toContain(".reader-status { grid-row:4;");
  });

  it("keeps the rendition host bounded during viewport scaling", () => {
    expect(readerStyles).toContain("height:100dvh");
    expect(readerStyles).toContain(".epub-container { min-width:0; min-height:0; height:100%");
    expect(readerStyles).toContain("grid-template-columns:minmax(0,1fr)");
    expect(readerStyles).toContain(".page-edge.previous { left:0;");
  });

  it("does not constrain epub.js's multi-column strip to one viewport", () => {
    expect(readerStyles).not.toContain(".epub-container>div");
    expect(readerStyles).not.toContain(".epub-container iframe");
    expect(readerStyles).toContain(".mode-paged .epub-container { width:min(100%,var(--reader-spread,1688px));");
  });

  it("themes reader popups from the selected reader palette", () => {
    expect(readerStyles).toContain("[data-reader-theme] { --reader-ui-surface:");
    expect(readerStyles).toContain("[data-reader-theme] .reader-overflow>div");
    expect(readerStyles).toContain("[data-reader-theme] .dictionary-popup");
    expect(readerStyles).toContain(".annotation-color-picker { position:fixed;");
  });

  it("keeps selection actions and dictionary content inside reader chrome", () => {
    expect(selectionToolbarPlacement(8, 400, 394, 62, 1920, 1080)).toEqual({ left: 12, top: 328 });
    expect(selectionToolbarPlacement(1912, 80, 394, 62, 1920, 1080)).toEqual({ left: 1514, top: 90 });
    expect(readerStyles).toContain("var(--radix-popover-content-available-height,");
    expect(readerStyles).toContain("left:var(--selection-toolbar-left)!important");
    expect(readerStyles).toContain("transform:none");
  });

  it("keeps a clicked search result highlighted until search closes", () => {
    expect(readerPageSource).toContain("bookbuddy-search-highlight");
    expect(readerPageSource).toContain("searchHighlightCfi.current = target");
    expect(readerPageSource).toContain("onClick={closeSearch}");
    expect(readerPageSource).not.toContain('navigation.current = "jump"; setSearchOpen(false); await rendition.current?.display(target)');
  });
});
