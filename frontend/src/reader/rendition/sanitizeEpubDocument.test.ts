import { describe, expect, it } from "vitest";
import { sanitizeEpubDocument } from "./sanitizeEpubDocument";

describe("hostile EPUB document sanitization", () => {
  it("removes executable elements, handlers, remote resources, and CSS imports", () => {
    document.body.innerHTML = `<script>alert(1)</script><iframe src="file:///secret"></iframe><form action="https://bad.example"><input></form><img onerror="alert(1)" src="https://bad.example/a.png" srcset="https://bad.example/a.png 2x"><a href="javascript:alert(1)">x</a><style>@import "https://bad.example/x.css";p{color:red}</style><p style="background:url(http://bad.example/a)">safe</p>`;
    sanitizeEpubDocument(document);
    expect(document.querySelector("script,iframe,form")).toBeNull();
    expect(document.querySelector("img")?.hasAttribute("onerror")).toBe(false);
    expect(document.querySelector("img")?.hasAttribute("src")).toBe(false);
    expect(document.querySelector("img")?.hasAttribute("srcset")).toBe(false);
    expect(document.querySelector("a")?.hasAttribute("href")).toBe(false);
    expect(document.querySelector("style")?.textContent).not.toContain("https:");
    expect(document.querySelector("p")?.getAttribute("style")).not.toContain("http:");
  });
});
