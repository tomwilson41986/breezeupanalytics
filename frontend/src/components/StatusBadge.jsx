import { statusBgColor } from "../lib/format";

export default function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold uppercase tracking-wider border ${statusBgColor(
        status
      )}`}
    >
      {status}
    </span>
  );
}
