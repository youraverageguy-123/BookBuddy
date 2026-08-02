import { useQuery } from "@tanstack/react-query";
import { sessionsQuery } from "../api/books";
import { readerLibraryQuery } from "../api/readerState";
import { useReaderStore } from "../store/readerStore";

export function useLibraryModel() {
  const userId = useReaderStore((state) => state.readerProfileId);
  const sessions = useQuery(sessionsQuery);
  const reader = useQuery({ ...readerLibraryQuery(userId ?? "missing"), enabled: Boolean(userId) });
  const stateBySession = new Map((reader.data?.books ?? []).map((item) => [item.session_key, item]));
  const bookmarksBySession = new Map<string, number>();
  for (const bookmark of reader.data?.bookmarks ?? []) bookmarksBySession.set(bookmark.session_key, (bookmarksBySession.get(bookmark.session_key) ?? 0) + 1);
  const annotationCounts = new Map(Object.entries(reader.data?.annotation_counts ?? {}));
  return { userId, sessions, reader, stateBySession, bookmarksBySession, annotationCounts, collections: reader.data?.collections ?? [], smart: reader.data?.smart_collections };
}
