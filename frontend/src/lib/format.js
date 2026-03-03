/**
 * Formatting utilities for BreezeVision
 */

export function formatCurrency(amount) {
  if (amount == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatCompact(amount) {
  if (amount == null) return "—";
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
  return formatCurrency(amount);
}

export function formatNumber(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US").format(n);
}

export function formatPercent(n, decimals = 1) {
  if (n == null) return "—";
  return `${n.toFixed(decimals)}%`;
}

export function formatBreezeTime(seconds) {
  if (seconds == null) return "—";
  return `${seconds.toFixed(1)}s`;
}

export function statusColor(status) {
  switch (status) {
    case "sold":
      return "text-emerald-600";
    case "rna":
      return "text-amber-600";
    case "out":
    case "withdrawn":
      return "text-red-500";
    default:
      return "text-gray-400";
  }
}

export function statusBgColor(status) {
  switch (status) {
    case "sold":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "rna":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "out":
    case "withdrawn":
      return "bg-red-50 text-red-600 border-red-200";
    default:
      return "bg-gray-50 text-gray-500 border-gray-200";
  }
}

export function sexLabel(code) {
  const map = { C: "Colt", F: "Filly", G: "Gelding", R: "Ridgling" };
  return map[code] || code;
}

export function colorLabel(code) {
  const map = {
    B: "Bay",
    CH: "Chestnut",
    DKB: "Dark Bay",
    BLK: "Black",
    GR: "Gray",
    RO: "Roan",
  };
  return map[code] || code;
}
