import { invoke } from "@tauri-apps/api/core";
import { performanceBudgetsMs, type PerformanceOperation } from "./budgets";

const samplesKey = "bookbuddy-performance-samples-v1";

export function recordPerformanceSample(operation: PerformanceOperation, durationMs: number): void {
  if (!Number.isFinite(durationMs) || durationMs < 0 || durationMs > 300_000) return;
  const sample = { operation, duration_ms: Math.round(durationMs * 100) / 100, budget_ms: performanceBudgetsMs[operation], timestamp: Date.now() };
  try {
    const current = JSON.parse(localStorage.getItem(samplesKey) ?? "[]") as unknown[];
    localStorage.setItem(samplesKey, JSON.stringify([...current.slice(-499), sample]));
  } catch { /* diagnostics never interfere with reading */ }
  if ("__TAURI_INTERNALS__" in window) void invoke("append_performance_sample", { operation, durationMs: sample.duration_ms }).catch(() => undefined);
}

export function afterStablePaint(startedAt: number, operation: PerformanceOperation): void {
  requestAnimationFrame(() => requestAnimationFrame(() => recordPerformanceSample(operation, performance.now() - startedAt)));
}
