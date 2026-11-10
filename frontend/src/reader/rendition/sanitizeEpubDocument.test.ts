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

  it("removes obfuscated schemes, protocol-relative URLs, and non-image data documents", () => {
    document.body.innerHTML = `<a id="tab" href="java&#9;script:alert(1)">x</a><a id="lead" href="&#1;javascript:alert(1)">x</a><img id="rel" src="//bad.example/a.png"><img id="back" src="\\\\bad.example\\a.png"><a id="data" href="data:text/html,<script>alert(1)</script>">x</a><img id="inline" src="data:image/png;base64,AAAA"><img id="local" src="../images/a.png"><p id="css" style="background:url(//bad.example/a)">safe</p>`;
    sanitizeEpubDocument(document);
    for (const id of ["tab", "lead", "data"]) expect(document.getElementById(id)?.hasAttribute("href")).toBe(false);
    for (const id of ["rel", "back"]) expect(document.getElementById(id)?.hasAttribute("src")).toBe(false);
    expect(document.getElementById("inline")?.getAttribute("src")).toBe("data:image/png;base64,AAAA");
    expect(document.getElementById("local")?.getAttribute("src")).toBe("../images/a.png");
    expect(document.getElementById("css")?.getAttribute("style")).not.toContain("bad.example");
  });
});
