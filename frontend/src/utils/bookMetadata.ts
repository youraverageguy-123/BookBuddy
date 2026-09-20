import type { ReaderBookState, Session } from "../types/contracts";

export interface EffectiveBookMetadata {
  title: string; author: string; description: string; series: string; publisher: string;
  language: string; publicationYear: string; genres: string[]; tags: string[];
  fileSizeBytes?: number; wordCount?: number; rating?: number | null;
}

export function effectiveBookMetadata(session: Session, state?: ReaderBookState): EffectiveBookMetadata {
  return {
    title: state?.title_override?.trim() || session.book_title,
    author: state?.author_override?.trim() || session.author || "Unavailable",
    description: state?.description_override?.trim() || session.description || "",
    series: state?.series_override?.trim() || session.series || "",
    publisher: session.publisher || "",
    language: session.language || "",
    publicationYear: formatPublicationYear(session.publication_year),
    genres: session.genres ?? [], tags: state?.tags ?? [], fileSizeBytes: session.source_size_bytes ?? undefined,
    wordCount: session.total_words ?? undefined, rating: state?.rating,
  };
}

export function formatBytes(value?: number): string {
  if (!value) return "Unavailable";
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(value?: number | null): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value * 1000)) : "Unavailable";
}

export function formatPublicationYear(value?: string | null): string {
  if (!value) return "Unavailable";
  return value.match(/\b\d{4}\b/)?.[0] ?? value;
}

export function metadataSearch(metadata: EffectiveBookMetadata, collectionNames: string[], query: string): { matches: boolean; reason: string } {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return { matches: true, reason: "" };
  const fields: Array<[string, string]> = [
    ["Title", metadata.title], ["Author", metadata.author], ["Series", metadata.series],
    ["Description", metadata.description], ["Publisher", metadata.publisher], ["Language", metadata.language],
    ["Genre", metadata.genres.join(" ")], ["Tag", metadata.tags.join(" ")], ["Collection", collectionNames.join(" ")],
  ];
  const matched = fields.find(([, value]) => value.toLocaleLowerCase().includes(needle));
  return { matches: Boolean(matched), reason: matched ? `Matched ${matched[0]}` : "" };
}
