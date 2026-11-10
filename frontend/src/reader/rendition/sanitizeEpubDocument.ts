const unsafeScheme = /^(?:javascript|vbscript|file|https?|ftp|wss?):/i;
const remoteCss = /@import\s+[^;]+;?|url\(\s*(['"]?)\s*(?:(?:https?|file|ftp|javascript|vbscript):|[/\\]{2})[^)]*\)/gi;
const urlAttributes = ["src", "href", "xlink:href", "poster", "action", "formaction", "data", "background", "ping"];

/**
 * Browsers ignore tabs, line breaks, and leading control characters when they
 * resolve a URL, so `java\tscript:` still runs. Compare against the same form.
 */
function normalizeUrl(value: string): string {
  return Array.from(value)
    .filter((character) => {
      const code = character.charCodeAt(0);
      return code > 0x20 && code !== 0x7f;
    })
    .join("");
}

function isUnsafeUrl(value: string): boolean {
  const url = normalizeUrl(value);
  if (unsafeScheme.test(url)) return true;
  // Protocol-relative URLs (`//host/x`, `\\host\x`) leave the book just like https: ones.
  if (/^[/\\]{2}/.test(url)) return true;
  // Embedded images are fine; any other data: document can carry markup or script.
  if (/^data:/i.test(url)) return !/^data:image\//i.test(url);
  return false;
}

export function sanitizeEpubDocument(document: Document): void {
  document.querySelectorAll("script, iframe, frame, object, embed, applet, form, base, meta[http-equiv='refresh' i]").forEach((node) => node.remove());
  document.querySelectorAll("style").forEach((node) => { node.textContent = (node.textContent ?? "").replace(remoteCss, ""); });
  document.querySelectorAll<HTMLElement>("*").forEach((node) => {
    for (const attribute of Array.from(node.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      if (name.startsWith("on") || (urlAttributes.includes(name) && isUnsafeUrl(value))) {
        node.removeAttribute(attribute.name);
      } else if (name === "srcset" && value.split(",").some((candidate) => isUnsafeUrl(candidate.trim()))) {
        node.removeAttribute(attribute.name);
      } else if (name === "style") {
        node.setAttribute(attribute.name, value.replace(remoteCss, ""));
      }
    }
  });
}
