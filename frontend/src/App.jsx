import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import LiveSales from "./pages/LiveSales";
import HistoricSales from "./pages/HistoricSales";
import SaleDetail from "./pages/SaleDetail";
import LotDetail from "./pages/LotDetail";
import SalesAnalysis from "./pages/SalesAnalysis";
import TimeAnalysis from "./pages/TimeAnalysis";
import PerformanceTracker from "./pages/PerformanceTracker";
import BreezePerformance from "./pages/BreezePerformance";
import Vendors from "./pages/Vendors";
import VendorSireAnalytics from "./pages/VendorSireAnalytics";
import BreezeScatter from "./pages/BreezeScatter";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<LiveSales />} />
          <Route path="live" element={<LiveSales />} />
          <Route path="historic" element={<HistoricSales />} />
          <Route path="sale/:saleKey" element={<SaleDetail />} />
          <Route path="sale/:saleKey/hip/:hipNumber" element={<LotDetail />} />
          <Route path="analysis/breeze-scatter" element={<BreezeScatter />} />
          <Route path="analytics/sales" element={<SalesAnalysis />} />
          <Route path="analytics/time" element={<TimeAnalysis />} />
          <Route path="analytics/performance" element={<PerformanceTracker />} />
          <Route path="analytics/breeze-performance" element={<BreezePerformance />} />
          <Route path="analytics/benchmarks" element={<VendorSireAnalytics />} />
          <Route path="vendors" element={<Vendors />} />
          <Route path="vendors/:tab" element={<Vendors />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
