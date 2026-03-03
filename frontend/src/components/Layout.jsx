import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#fafafa]">
      <Sidebar />

      {/* Main content — offset by sidebar width */}
      <main className="ml-[240px] min-h-screen">
        <div className="max-w-[1200px] mx-auto px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
