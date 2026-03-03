import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { SALE_CATALOG } from "../lib/api";

/* ── Organize sales by category ─────────────────────────── */

const historicByYear = Object.entries(SALE_CATALOG)
  .filter(([, m]) => !m.isLive)
  .sort(([, a], [, b]) => b.year - a.year || a.month - b.month)
  .reduce((acc, [key, meta]) => {
    if (!acc[meta.year]) acc[meta.year] = [];
    acc[meta.year].push({ key, meta });
    return acc;
  }, {});

const historicYears = Object.keys(historicByYear).sort((a, b) => b - a);

const liveSales = Object.entries(SALE_CATALOG)
  .filter(([, m]) => m.isLive && m.month === 3)
  .sort(([, a], [, b]) => a.month - b.month);

function shortName(meta) {
  if (meta.month === 3) return "March 2YO";
  if (meta.month === 4) return "Spring 2YO";
  if (meta.month === 6) return "June 2YO & HRA";
  return meta.name;
}

/* ── Sidebar ────────────────────────────────────────────── */

export default function Sidebar() {
  const location = useLocation();
  const [expandedYears, setExpandedYears] = useState({});

  // Auto-expand the year group that contains the currently active sale
  useEffect(() => {
    const match = location.pathname.match(/^\/sale\/(obs_\w+_(\d{4}))/);
    if (match) {
      const year = match[2];
      setExpandedYears((prev) => (prev[year] ? prev : { ...prev, [year]: true }));
    }
  }, [location.pathname]);

  function toggleYear(year) {
    setExpandedYears((prev) => ({ ...prev, [year]: !prev[year] }));
  }

  return (
    <aside className="fixed top-0 left-0 bottom-0 w-[240px] bg-white border-r border-gray-200/80 flex flex-col z-40">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-gray-100 shrink-0">
        <NavLink to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
            <svg
              viewBox="0 0 24 24"
              className="w-4 h-4 text-white"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
          </div>
          <span className="text-[15px] font-semibold tracking-tight text-gray-900">
            Breeze<span className="text-brand-600">Vision</span>
          </span>
        </NavLink>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 pt-4 pb-4 space-y-5 overflow-y-auto sidebar-scroll">
        {/* ── Live Sales ────────────────────────────────── */}
        <Section label="Live Sales" icon={<LiveIcon />}>
          {liveSales.map(([key, meta]) => (
            <NavLink
              key={key}
              to={`/sale/${key}`}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-700 font-medium"
                    : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                }`
              }
            >
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              {shortName(meta)}
            </NavLink>
          ))}
        </Section>

        {/* ── Analytics Tools ───────────────────────────── */}
        <Section label="Analytics Tools" icon={<AnalyticsIcon />}>
          <NavLink
            to="/analytics"
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] transition-colors ${
                isActive
                  ? "bg-brand-50 text-brand-700 font-medium"
                  : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
              }`
            }
          >
            Sale Analytics
          </NavLink>
        </Section>

        {/* ── Vendors ───────────────────────────────────── */}
        <Section label="Vendors" icon={<VendorsIcon />}>
          <NavLink
            to="/vendors"
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-[13px] transition-colors ${
                isActive
                  ? "bg-brand-50 text-brand-700 font-medium"
                  : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
              }`
            }
          >
            Vendor Performance
          </NavLink>
        </Section>

        {/* ── Historic Sales ────────────────────────────── */}
        <Section label="Historic Sales" icon={<ArchiveIcon />}>
          {historicYears.map((year) => (
            <div key={year}>
              <button
                onClick={() => toggleYear(year)}
                className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-[13px] transition-colors ${
                  expandedYears[year]
                    ? "text-gray-900 font-medium"
                    : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                }`}
              >
                <ChevronIcon expanded={expandedYears[year]} />
                <span>{year} Season</span>
              </button>
              {expandedYears[year] && (
                <div className="ml-6 mt-0.5 space-y-0.5 border-l border-gray-100 pl-2">
                  {historicByYear[year].map((s) => (
                    <NavLink
                      key={s.key}
                      to={`/sale/${s.key}`}
                      className={({ isActive }) =>
                        `block px-2.5 py-1 rounded text-[12px] transition-colors ${
                          isActive
                            ? "bg-brand-50 text-brand-700 font-medium"
                            : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                        }`
                      }
                    >
                      {shortName(s.meta)}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          ))}
        </Section>
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-gray-100 shrink-0">
        <p className="text-[11px] text-gray-400">
          Data sourced from OBS &amp; S3
        </p>
      </div>
    </aside>
  );
}

/* ── Sub-components ──────────────────────────────────────── */

function Section({ label, icon, children }) {
  return (
    <div>
      <div className="flex items-center gap-2 px-3 mb-1.5">
        <span className="text-gray-400">{icon}</span>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
          {label}
        </p>
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function ChevronIcon({ expanded }) {
  return (
    <svg
      className={`w-3.5 h-3.5 text-gray-400 transition-transform ${
        expanded ? "rotate-90" : ""
      }`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

/* ── Icons ───────────────────────────────────────────────── */

function ArchiveIcon() {
  return (
    <svg
      className="w-3.5 h-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="2" y="3" width="20" height="5" rx="1" />
      <path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" />
      <line x1="10" y1="12" x2="14" y2="12" />
    </svg>
  );
}

function LiveIcon() {
  return (
    <svg
      className="w-3.5 h-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

function AnalyticsIcon() {
  return (
    <svg
      className="w-3.5 h-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

function VendorsIcon() {
  return (
    <svg
      className="w-3.5 h-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}
