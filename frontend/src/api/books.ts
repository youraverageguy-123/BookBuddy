import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { z } from "zod";
import { apiArrayBuffer, apiRequest, backendConnection, encoded } from "./client";
import { bookSchema, loadSchema, sessionsSchema, uploadSchema } from "../types/contracts";

export const booksApi = {
  sessions: () => apiRequest("/sessions", sessionsSchema),
  load: (book: string, session: string) => apiRequest(`/load/${encoded(book)}/${encoded(session)}`, loadSchema, { method: "POST" }),
  metadata: (book: string, session: string) => apiRequest(`/book/${encoded(book)}/${encoded(session)}`, bookSchema),
  epub: (book: string, session: string) => apiArrayBuffer(`/reader/${encoded(book)}/${encoded(session)}/epub`),
  cover: (book: string, session: string, size: 160 | 320 | 640 = 320) => apiArrayBuffer(`/reader/${encoded(book)}/${encoded(session)}/cover?size=${size}`),
  /** Stores a rendered first page as the cover of a PDF. */
  uploadCover: async (book: string, session: string, image: Blob): Promise<void> => {
    const connection = await backendConnection();
    const headers = new Headers({ "Content-Type": image.type || "image/jpeg" });
    if (connection.token) headers.set("Authorization", `Bearer ${connection.token}`);
    const response = await fetch(`${connection.baseUrl}/reader/${encoded(book)}/${encoded(session)}/cover`, { method: "PUT", headers, body: image });
    if (!response.ok) throw new Error(`Could not save cover (${response.status})`);
  },
  exportNotes: (userId:string, book:string, session:string) => apiArrayBuffer(`/reader/${encoded(userId)}/books/${encoded(book)}/${encoded(session)}/annotations/export`),
  rename: (book:string,session:string,label:string) => { const form=new FormData(); form.set("label",label); return apiRequest(`/session/${encoded(book)}/${encoded(session)}/rename`,z.object({session:z.unknown()}),{method:"POST",body:form}); },
  softDelete: (book:string,session:string) => apiRequest(`/session/${encoded(book)}/${encoded(session)}/delete`,z.object({session:z.unknown()}),{method:"POST"}),
  restore: (book:string,session:string) => apiRequest(`/session/${encoded(book)}/${encoded(session)}/restore`,z.object({session:z.unknown()}),{method:"POST"}),
  uploadDesktopPath: async (path: string) => {
    const connection = await backendConnection();
    const payload = await invoke<unknown>("upload_epub", { path, connection, sessionName: "Reading" });
    return uploadSchema.parse(payload);
  },
  uploadDesktop: async () => {
    const selected = await open({ multiple: false, filters: [{ name: "Books", extensions: ["epub", "pdf"] }] });
    if (!selected) return null;
    return booksApi.uploadDesktopPath(selected);
  },
  uploadWeb: async (file: File) => {
    const form = new FormData(); form.set("file", file); form.set("session_name", "Reading");
    return apiRequest("/upload", uploadSchema, { method: "POST", body: form });
  },
};

export const sessionsQuery = { queryKey: ["sessions"] as const, queryFn: booksApi.sessions };

export const sessionRouteSchema = z.object({ book: z.string().min(1), session: z.string().min(1) });
