import { describe, expect, it, vi } from "vitest";
import { annotationStyles, normalizeAnnotationColor, syncRenditionAnnotations } from "./annotationRendering";

describe("reader annotation rendering", () => {
  it("normalizes legacy colors and rejects unsafe values", () => {
    expect(normalizeAnnotationColor("gold", "highlight")).toBe("#f6c85f");
    expect(normalizeAnnotationColor("#A78BFA", "underline")).toBe("#a78bfa");
    expect(normalizeAnnotationColor("url(javascript:bad)", "underline")).toBe("#5dade2");
  });

  it("uses visible theme-independent SVG styles", () => {
    expect(annotationStyles("highlight", "#f6c85f")).toMatchObject({ fill: "#f6c85f", "mix-blend-mode": "normal" });
    expect(annotationStyles("underline", "#5dade2")).toMatchObject({ stroke: "#5dade2", "stroke-width": "2" });
  });

  it("adds, recolors, and removes EPUB annotations", () => {
    const api = { highlight: vi.fn(), underline: vi.fn(), remove: vi.fn() };
    let rendered = syncRenditionAnnotations(api, new Map(), [
      { annotation_id: "one", cfi_range: "epubcfi(/6/2)", annotation_type: "highlight", color: "#f6c85f" },
      { annotation_id: "note", cfi_range: "epubcfi(/6/4)", annotation_type: "note", color: "gold" },
    ]);
    expect(api.highlight).toHaveBeenCalledOnce();
    expect(api.underline).not.toHaveBeenCalled();

    rendered = syncRenditionAnnotations(api, rendered, [
      { annotation_id: "one", cfi_range: "epubcfi(/6/2)", annotation_type: "highlight", color: "#6ecb8b" },
    ]);
    expect(api.remove).toHaveBeenCalledWith("epubcfi(/6/2)", "highlight");
    expect(api.highlight).toHaveBeenCalledTimes(2);

    syncRenditionAnnotations(api, rendered, []);
    expect(api.remove).toHaveBeenLastCalledWith("epubcfi(/6/2)", "highlight");
  });
});
