export interface StartupBookState {
  session_key: string;
  last_opened_at?: number | null;
}

export type StartupDestination = "home" | "library" | "resume";

export function startupDestinationHash(
  desktop: boolean,
  currentHash: string,
  preference: StartupDestination,
  books: StartupBookState[],
): string | null {
  // Native startup always restores state before landing on Home. It must
  // never reopen the previously active route or book automatically.
  if (desktop) return "#/";
  if (currentHash && currentHash !== "#/") return null;
  if (preference === "library") return "#/library";
  if (preference !== "resume") return null;
  const recent = [...books].sort((left, right) => (right.last_opened_at ?? 0) - (left.last_opened_at ?? 0))[0];
  if (!recent) return null;
  const separator = recent.session_key.indexOf("::");
  if (separator <= 0) return null;
  return `#/reader/${encodeURIComponent(recent.session_key.slice(0, separator))}/${encodeURIComponent(recent.session_key.slice(separator + 2))}`;
}
