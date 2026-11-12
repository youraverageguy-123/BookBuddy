import { create } from "zustand";

export type ToastKind = "success" | "error" | "info";
export interface Toast { id: number; kind: ToastKind; message: string }
interface ToastState { toasts: Toast[]; push: (kind: ToastKind, message: string) => void; dismiss: (id: number) => void }

const MAX_VISIBLE = 3;
let nextId = 1;

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  // Showing the same message twice in a row adds nothing, so repeats are dropped.
  push: (kind, message) => set((state) => state.toasts.some((item) => item.message === message && item.kind === kind)
    ? state
    : { toasts: [...state.toasts, { id: nextId++, kind, message }].slice(-MAX_VISIBLE) }),
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((item) => item.id !== id) })),
}));

/** Brief confirmations and failures that should be noticed wherever the reader is looking. */
export const toast = {
  success: (message: string) => useToasts.getState().push("success", message),
  error: (message: string) => useToasts.getState().push("error", message),
  info: (message: string) => useToasts.getState().push("info", message),
};
