import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import LiveSales from "./pages/LiveSales";
import HistoricSales from "./pages/HistoricSales";
import SaleDetail from "./pages/SaleDetail";
import LotDetail from "./pages/LotDetail";
import Analytics from "./pages/Analytics";
import Vendors from "./pages/Vendors";

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
          <Route path="analytics" element={<Analytics />} />
          <Route path="vendors" element={<Vendors />} />
          <Route path="vendors/:tab" element={<Vendors />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
