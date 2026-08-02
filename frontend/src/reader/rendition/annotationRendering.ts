export type VisualAnnotationType = "highlight" | "underline";

export interface VisualAnnotation {
  annotation_id: string;
  cfi_range: string;
  annotation_type: "highlight" | "underline" | "note";
  color: string;
}

export interface RenditionAnnotationApi {
  highlight: (cfiRange: string, data?: object, callback?: (...args: unknown[]) => unknown, className?: string, styles?: object) => unknown;
  underline: (cfiRange: string, data?: object, callback?: (...args: unknown[]) => unknown, className?: string, styles?: object) => unknown;
  remove: (cfiRange: string, type: string) => void;
}

export interface RenderedAnnotation {
  cfiRange: string;
  type: VisualAnnotationType;
  color: string;
}

export const annotationColorPresets = [
  { name: "Gold", value: "#f6c85f" },
  { name: "Green", value: "#6ecb8b" },
  { name: "Blue", value: "#5dade2" },
  { name: "Pink", value: "#f08db4" },
  { name: "Orange", value: "#f2994a" },
  { name: "Purple", value: "#a78bfa" },
] as const;

const defaultColors: Record<VisualAnnotationType, string> = { highlight: "#f6c85f", underline: "#5dade2" };
const legacyColors: Record<string, string> = { gold: "#f6c85f", yellow: "#f6c85f", green: "#6ecb8b", blue: "#5dade2", pink: "#f08db4", orange: "#f2994a", purple: "#a78bfa" };

export function normalizeAnnotationColor(color: string | undefined, type: VisualAnnotationType): string {
  const candidate = color?.trim().toLowerCase() ?? "";
  if (/^#[0-9a-f]{6}$/.test(candidate)) return candidate;
  return legacyColors[candidate] ?? defaultColors[type];
}

export function annotationStyles(type: VisualAnnotationType, color: string): Record<string, string> {
  const safeColor = normalizeAnnotationColor(color, type);
  return type === "highlight"
    ? { fill: safeColor, "fill-opacity": "0.48", "mix-blend-mode": "normal" }
    : { stroke: safeColor, "stroke-opacity": "0.95", "stroke-width": "2", "mix-blend-mode": "normal" };
}

export function syncRenditionAnnotations(
  api: RenditionAnnotationApi,
  previous: Map<string, RenderedAnnotation>,
  annotations: VisualAnnotation[],
): Map<string, RenderedAnnotation> {
  const next = new Map<string, RenderedAnnotation>();
  for (const item of annotations) {
    if (item.annotation_type === "note") continue;
    const type = item.annotation_type;
    const color = normalizeAnnotationColor(item.color, type);
    const key = `${type}:${item.cfi_range}`;
    next.set(key, { cfiRange: item.cfi_range, type, color });
  }

  for (const [key, current] of previous) {
    const replacement = next.get(key);
    if (!replacement || replacement.color !== current.color) api.remove(current.cfiRange, current.type);
  }

  for (const [key, current] of next) {
    const existing = previous.get(key);
    if (existing?.color === current.color) continue;
    api[current.type](current.cfiRange, { color: current.color }, undefined, `bookbuddy-${current.type}`, annotationStyles(current.type, current.color));
  }
  return next;
}
