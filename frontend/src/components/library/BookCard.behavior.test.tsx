import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Session } from "../../types/contracts";
import { BookActionController, BookCard } from "./BookCard";

const { softDelete, restore, exportNotes, updateBook, setCollectionMember, setLibraryPreferences } = vi.hoisted(() => ({
  softDelete: vi.fn(),
  restore: vi.fn(),
  exportNotes: vi.fn(),
  updateBook: vi.fn(),
  setCollectionMember: vi.fn(),
  setLibraryPreferences: vi.fn(),
}));

vi.mock("../../api/books", () => ({
  booksApi: { softDelete: (...args: unknown[]) => softDelete(...args), restore: (...args: unknown[]) => restore(...args), exportNotes: (...args: unknown[]) => exportNotes(...args) },
}));

vi.mock("../../api/readerState", () => ({
  readerStateApi: { updateBook: (...args: unknown[]) => updateBook(...args), setCollectionMember: (...args: unknown[]) => setCollectionMember(...args) },
}));

vi.mock("../../store/readerStore", () => {
  const state = {
    library: { pinnedSessionKeys: [] },
    setLibraryPreferences,
  };
  return { useReaderStore: (selector: (value: typeof state) => unknown) => selector(state) };
});

vi.mock("./BookCover", () => ({
  BookCover: ({ title }: { title: string }) => <div>{title} cover</div>,
}));

const session: Session = {
  session_key: "red-rising::default",
  book_name: "red-rising",
  session_name: "default",
  book_title: "Red Rising",
  author: "Pierce Brown",
  total_chapters: 44,
  analysis: { status: "ready" },
  reader_analysis: { schema_version: "reader_analysis_v1", session_key: "red-rising::default", state: "idle", progress: 0, jobs: [] },
};

function renderWithProviders(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

describe("book action overlays", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("portals Book Info outside its card and dismisses it from the backdrop or Escape", async () => {
    const user = userEvent.setup();
    const view = renderWithProviders(<BookCard session={session} userId="reader" collections={[]} />);

    await user.click(screen.getByRole("button", { name: "More actions for Red Rising" }));
    await user.click(screen.getByRole("menuitem", { name: "Book Info" }));

    const dialog = screen.getByRole("dialog", { name: "Red Rising" });
    expect(view.container.contains(dialog)).toBe(false);
    await user.click(within(dialog).getByText("Pierce Brown"));
    expect(dialog).toBeInTheDocument();

    fireEvent.click(dialog.parentElement!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "More actions for Red Rising" }));
    await user.click(screen.getByRole("menuitem", { name: "Book Info" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the shared actions menu from a specialized Home cover on right click", () => {
    renderWithProviders(<BookActionController session={session} userId="reader" collections={[]}>
      {({ showContextMenu }) => <button onContextMenu={showContextMenu}>Home cover</button>}
    </BookActionController>);

    fireEvent.contextMenu(screen.getByRole("button", { name: "Home cover" }), { clientX: 120, clientY: 160 });
    expect(screen.getByRole("menu", { name: "Actions for Red Rising" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Book Info" })).toBeInTheDocument();
  });

  it("hides a successfully removed card immediately while Undo is available", async () => {
    softDelete.mockResolvedValue({ session: {} });
    const user = userEvent.setup();
    renderWithProviders(<BookCard session={session} userId="reader" collections={[]} />);

    await user.click(screen.getByRole("button", { name: "More actions for Red Rising" }));
    await user.click(screen.getByRole("menuitem", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Remove from Library" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Removed from Library");
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("shows visible confirmation when a book is pinned", async () => {
    const user = userEvent.setup();
    renderWithProviders(<BookCard session={session} userId="reader" collections={[]} />);

    await user.click(screen.getByRole("button", { name: "More actions for Red Rising" }));
    await user.click(screen.getByRole("menuitem", { name: "Pin to Start" }));

    expect(setLibraryPreferences).toHaveBeenCalledWith({ pinnedSessionKeys: [session.session_key] });
    expect(screen.getByRole("status")).toHaveTextContent("Pinned to Start");
  });

  it("toggles collection membership from the shared context menu", async () => {
    setCollectionMember.mockResolvedValue({ collection: {} });
    const user = userEvent.setup();
    const collections = [{ collection_id:"space", name:"Space", sort_order:0, session_keys:[], description:"", pinned:false, book_sort:"recent" }];
    renderWithProviders(<BookCard session={session} userId="reader" collections={collections} />);

    await user.click(screen.getByRole("button", { name: "More actions for Red Rising" }));
    await user.click(screen.getByRole("menuitemcheckbox", { name: "Space" }));

    expect(setCollectionMember).toHaveBeenCalledWith("reader", "space", session.session_key, true);
    expect(await screen.findByRole("status")).toHaveTextContent("Added to collection");
  });
});
