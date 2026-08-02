import { invoke } from "@tauri-apps/api/core";
import type { ZodType } from "zod";

export interface BackendConnection { baseUrl: string; token: string | null; managed: boolean }

export class ApiRequestError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
  }
}

let cachedConnection: BackendConnection | null = null;
let pendingConnection: Promise<BackendConnection> | null = null;

const isTauri = (): boolean => "__TAURI_INTERNALS__" in window;

export async function backendConnection(force = false): Promise<BackendConnection> {
  if (cachedConnection && !force) return cachedConnection;
  if (pendingConnection && !force) return pendingConnection;
  if (isTauri()) {
    pendingConnection = invoke<BackendConnection>("backend_connection");
  } else {
    pendingConnection = Promise.resolve({ baseUrl: import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000", token: null, managed: false });
  }
  try {
    cachedConnection = await pendingConnection;
  } finally {
    pendingConnection = null;
  }
  return cachedConnection;
}

export async function apiRequest<T>(path: string, schema: ZodType<T>, init: RequestInit = {}): Promise<T> {
  const connection = await backendConnection();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (connection.token) headers.set("Authorization", `Bearer ${connection.token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${connection.baseUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail = payload && typeof payload === "object" && "detail" in payload ? JSON.stringify(payload.detail) : response.statusText;
    throw new ApiRequestError(response.status, detail || `BookBuddy request failed (${response.status})`);
  }
  return schema.parse(await response.json());
}

export async function apiArrayBuffer(path: string): Promise<ArrayBuffer> {
  const connection = await backendConnection();
  const headers = new Headers();
  if (connection.token) headers.set("Authorization", `Bearer ${connection.token}`);
  const response = await fetch(`${connection.baseUrl}${path}`, { headers });
  if (!response.ok) throw new Error(`Could not load EPUB (${response.status})`);
  return response.arrayBuffer();
}

export const encoded = (value: string): string => encodeURIComponent(value);
