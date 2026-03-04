import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#fafafa]">
      <Sidebar />

      {/* Main content — offset by sidebar width */}
      <main className="ml-[220px] min-h-screen">
        <div className="max-w-[1400px] mx-auto px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
