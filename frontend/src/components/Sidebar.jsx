import { NavLink } from "react-router-dom";

const navLinks = [
  { to: "/", label: "Dashboard", icon: DashboardIcon },
  { to: "/analytics", label: "Analytics", icon: AnalyticsIcon },
];

export default function Sidebar() {
  return (
    <aside className="fixed top-0 left-0 bottom-0 w-[240px] bg-white border-r border-gray-200/80 flex flex-col z-40">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-gray-100">
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
      <nav className="flex-1 px-3 pt-6 space-y-1">
        <p className="px-3 mb-2 text-[11px] font-medium uppercase tracking-wider text-gray-400">
          Menu
        </p>
        {navLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                isActive
                  ? "bg-brand-50 text-brand-700 font-medium"
                  : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
              }`
            }
          >
            <link.icon className="w-[18px] h-[18px]" />
            {link.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-gray-100">
        <p className="text-[11px] text-gray-400">
          Data sourced from OBS
        </p>
      </div>
    </aside>
  );
}

/* Icons — thin, clean stroke style */
function DashboardIcon({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  );
}

function AnalyticsIcon({ className }) {
  return (
    <svg
      className={className}
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
