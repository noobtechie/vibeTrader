import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(
  value: number | null | undefined,
  currency = "CAD"
): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

export function formatPnL(value: number | null | undefined): {
  text: string;
  className: string;
} {
  if (value == null) return { text: "—", className: "text-neutral-400" };
  const isProfit = value >= 0;
  return {
    text: formatCurrency(value),
    className: isProfit ? "text-profit" : "text-loss",
  };
}

export function formatRMultiple(r: number | null | undefined): string {
  if (r == null) return "—";
  return `${r >= 0 ? "+" : ""}${r.toFixed(2)}R`;
}
