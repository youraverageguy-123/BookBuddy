import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useEffect } from "react";
import { useToasts, type Toast } from "./toast";

const icons = { success: CheckCircle2, error: AlertCircle, info: Info } as const;

function ToastItem({ item }: { item: Toast }) {
  const dismiss = useToasts((state) => state.dismiss);
  useEffect(() => {
    // Errors stay longer: they usually need reading twice.
    const timer = window.setTimeout(() => dismiss(item.id), item.kind === "error" ? 8000 : 4000);
    return () => window.clearTimeout(timer);
  }, [dismiss, item.id, item.kind]);
  const Icon = icons[item.kind];
  return <li className={`toast toast-${item.kind}`} role={item.kind === "error" ? "alert" : "status"}>
    <Icon aria-hidden="true"/><span>{item.message}</span>
    <button type="button" aria-label="Dismiss message" onClick={() => dismiss(item.id)}><X/></button>
  </li>;
}

export function Toaster() {
  const toasts = useToasts((state) => state.toasts);
  return <ol className="toaster" aria-label="Notifications">{toasts.map((item) => <ToastItem key={item.id} item={item}/>)}</ol>;
}
