const unsafeUrl = /^(?:javascript|vbscript|file|https?|ftp):/i;
const remoteCss = /@import\s+[^;]+;?|url\(\s*(['"]?)(?:https?|file|ftp|javascript):[^)]*\)/gi;

export function sanitizeEpubDocument(document: Document): void {
  document.querySelectorAll("script, iframe, object, embed, form, base, meta[http-equiv='refresh' i]").forEach((node) => node.remove());
  document.querySelectorAll("style").forEach((node) => { node.textContent = (node.textContent ?? "").replace(remoteCss, ""); });
  document.querySelectorAll<HTMLElement>("*").forEach((node) => {
    for (const attribute of Array.from(node.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      if (name.startsWith("on") || (["src", "href", "xlink:href", "poster", "action", "formaction"].includes(name) && unsafeUrl.test(value))) {
        node.removeAttribute(attribute.name);
      } else if (name === "srcset" && value.split(",").some((candidate) => unsafeUrl.test(candidate.trim()))) {
        node.removeAttribute(attribute.name);
      } else if (name === "style") {
        node.setAttribute(attribute.name, value.replace(remoteCss, ""));
      }
    }
  });
}
