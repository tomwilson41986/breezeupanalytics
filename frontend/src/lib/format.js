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
      return "text-accent-400";
    case "rna":
      return "text-warm-400";
    case "out":
    case "withdrawn":
      return "text-danger-400";
    default:
      return "text-slate-400";
  }
}

export function statusBgColor(status) {
  switch (status) {
    case "sold":
      return "bg-accent-500/15 text-accent-400 border-accent-500/30";
    case "rna":
      return "bg-warm-500/15 text-warm-400 border-warm-500/30";
    case "out":
    case "withdrawn":
      return "bg-danger-500/15 text-danger-400 border-danger-500/30";
    default:
      return "bg-slate-500/15 text-slate-400 border-slate-500/30";
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
