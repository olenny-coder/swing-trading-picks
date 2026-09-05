export function formatPrice(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v >= 1000
    ? v.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : v.toFixed(2);
}

export function formatPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(1)}%`;
}

export function formatDate(v: string | null | undefined): string {
  if (!v) return "—";
  return new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatDateTime(v: string | null | undefined): string {
  if (!v) return "—";
  return new Date(v).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function confidenceLabel(v: number): "High" | "Medium" | "Low" {
  if (v >= 71) return "High";
  if (v >= 41) return "Medium";
  return "Low";
}
