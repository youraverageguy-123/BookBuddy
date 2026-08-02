import type { ReaderFont } from "../store/readerStore";

export interface ReaderFontOption {
  id: ReaderFont;
  label: string;
  family: string;
  description: string;
  group: "Microsoft & Windows" | "Bundled open fonts";
}

export const readerFontOptions: readonly ReaderFontOption[] = [
  { id: "segoe-ui", label: "Segoe UI", family: "Segoe UI, Arial, sans-serif", description: "Windows default UI font", group: "Microsoft & Windows" },
  { id: "segoe-print", label: "Segoe Print", family: "Segoe Print, cursive", description: "Informal Microsoft handwriting", group: "Microsoft & Windows" },
  { id: "segoe-script", label: "Segoe Script", family: "Segoe Script, cursive", description: "Microsoft script face", group: "Microsoft & Windows" },
  { id: "georgia", label: "Georgia", family: "Georgia, serif", description: "Windows book serif", group: "Microsoft & Windows" },
  { id: "cambria", label: "Cambria", family: "Cambria, Georgia, serif", description: "Microsoft serif", group: "Microsoft & Windows" },
  { id: "calibri", label: "Calibri", family: "Calibri, Arial, sans-serif", description: "Microsoft sans serif", group: "Microsoft & Windows" },
  { id: "candara", label: "Candara", family: "Candara, sans-serif", description: "Microsoft humanist sans", group: "Microsoft & Windows" },
  { id: "constantia", label: "Constantia", family: "Constantia, serif", description: "Microsoft reading serif", group: "Microsoft & Windows" },
  { id: "corbel", label: "Corbel", family: "Corbel, sans-serif", description: "Microsoft screen sans", group: "Microsoft & Windows" },
  { id: "times-new-roman", label: "Times New Roman", family: "Times New Roman, Times, serif", description: "Classic Windows serif", group: "Microsoft & Windows" },
  { id: "arial", label: "Arial", family: "Arial, sans-serif", description: "Windows sans serif", group: "Microsoft & Windows" },
  { id: "bahnschrift", label: "Bahnschrift", family: "Bahnschrift, sans-serif", description: "Windows variable sans", group: "Microsoft & Windows" },
  { id: "consolas", label: "Consolas", family: "Consolas, monospace", description: "Microsoft monospaced", group: "Microsoft & Windows" },
  { id: "courier-new", label: "Courier New", family: "Courier New, monospace", description: "Classic monospaced", group: "Microsoft & Windows" },
  { id: "franklin-gothic", label: "Franklin Gothic", family: "Franklin Gothic Medium, Arial, sans-serif", description: "Windows grotesque sans", group: "Microsoft & Windows" },
  { id: "palatino", label: "Palatino Linotype", family: "Palatino Linotype, Palatino, serif", description: "Windows old-style serif", group: "Microsoft & Windows" },
  { id: "sitka", label: "Sitka Text", family: "Sitka Text, Georgia, serif", description: "Microsoft optical-size serif", group: "Microsoft & Windows" },
  { id: "tahoma", label: "Tahoma", family: "Tahoma, sans-serif", description: "Compact Windows sans", group: "Microsoft & Windows" },
  { id: "verdana", label: "Verdana", family: "Verdana, sans-serif", description: "Screen sans serif", group: "Microsoft & Windows" },
  { id: "trebuchet", label: "Trebuchet MS", family: "Trebuchet MS, sans-serif", description: "Humanist Windows sans", group: "Microsoft & Windows" },
  { id: "literata", label: "Literata", family: "Literata, Georgia, serif", description: "Literary serif", group: "Bundled open fonts" },
  { id: "source-serif", label: "Source Serif 4", family: "Source Serif 4, Georgia, serif", description: "Clear book serif", group: "Bundled open fonts" },
  { id: "eb-garamond", label: "EB Garamond", family: "EB Garamond, Georgia, serif", description: "Classic old-style serif", group: "Bundled open fonts" },
  { id: "crimson", label: "Crimson Pro", family: "Crimson Pro, Georgia, serif", description: "Warm long-form serif", group: "Bundled open fonts" },
  { id: "inter", label: "Inter", family: "Inter, sans-serif", description: "Clean sans serif", group: "Bundled open fonts" },
  { id: "atkinson", label: "Atkinson Hyperlegible", family: "Atkinson Hyperlegible, sans-serif", description: "High-legibility sans", group: "Bundled open fonts" },
  { id: "source-sans", label: "Source Sans 3", family: "Source Sans 3, sans-serif", description: "Humanist sans serif", group: "Bundled open fonts" },
  { id: "system", label: "System serif", family: "Georgia, serif", description: "Built into Windows", group: "Microsoft & Windows" },
] as const;

export function readerFontFamily(font: ReaderFont): string {
  return readerFontOptions.find((option) => option.id === font)?.family ?? "Georgia, serif";
}

export const offlineReaderFonts = `
@font-face{font-family:"Literata";src:url("/fonts/literata-regular.woff2") format("woff2");font-display:swap}
@font-face{font-family:"Source Serif 4";src:url("/fonts/source-serif-4-regular.woff2") format("woff2");font-display:swap}
@font-face{font-family:"EB Garamond";src:url("/fonts/eb-garamond-regular.woff2") format("woff2");font-display:swap}
@font-face{font-family:"Crimson Pro";src:url("/fonts/crimson-pro-regular.woff2") format("woff2");font-display:swap}
@font-face{font-family:"Inter";src:url("/fonts/inter-regular.woff2") format("woff2");font-display:swap}
@font-face{font-family:"Atkinson Hyperlegible";src:url("/fonts/atkinson-hyperlegible-regular.woff2") format("woff2");font-display:swap}
@font-face{font-family:"Source Sans 3";src:url("/fonts/source-sans-3-regular.woff2") format("woff2");font-display:swap}
`;
