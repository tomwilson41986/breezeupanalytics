/**
 * Convert historic sales Excel data to JSON files for the frontend.
 *
 * Input:  data/historic-sales/USA 2yo Sales Results 2015 - 2025.xlsx
 * Output: frontend/public/data/historic/*.json
 */
import { readFile, writeFile, mkdir } from "fs/promises";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import XLSX from "xlsx";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const EXCEL_PATH = join(ROOT, "data/historic-sales/USA 2yo Sales Results 2015 - 2025.xlsx");
const OUT_DIR = join(ROOT, "frontend/public/data/historic");

async function main() {
  await mkdir(OUT_DIR, { recursive: true });

  const buf = await readFile(EXCEL_PATH);
  const workbook = XLSX.read(buf, { type: "buffer" });

  console.log("Sheets found:", workbook.SheetNames);

  // 1. Parse "Vendors" sheet → historic-vendors.json
  const vendorsSheet = workbook.Sheets["Vendors"];
  const vendorsRaw = XLSX.utils.sheet_to_json(vendorsSheet);
  const vendors = vendorsRaw
    .filter((r) => r.Vendor && r.Vendor !== "Grand Total")
    .map((r) => ({
      vendor: r.Vendor,
      runners: r.Runner || 0,
      winners: r.Winner || 0,
      winPct: r["%Wnr"] != null ? +(r["%Wnr"] * 100).toFixed(1) : 0,
      stakesWinners: r.StakesWinner || 0,
      stakesWinPct: r["%StksWnr"] != null ? +(r["%StksWnr"] * 100).toFixed(1) : 0,
      gradedStakesWinners: r.GrdStakesWinner || 0,
      gradedStakesWinPct: r["%GrdStksWnr"] != null ? +(r["%GrdStksWnr"] * 100).toFixed(1) : 0,
      g1Winners: r.G1Winner || 0,
      g1WinPct: r["%G1Wnr"] != null ? +(r["%G1Wnr"] * 100).toFixed(1) : 0,
    }));

  // Extract grand total
  const grandTotalRow = vendorsRaw.find((r) => r.Vendor === "Grand Total");
  const grandTotal = grandTotalRow
    ? {
        runners: grandTotalRow.Runner || 0,
        winners: grandTotalRow.Winner || 0,
        winPct: grandTotalRow["%Wnr"] != null ? +(grandTotalRow["%Wnr"] * 100).toFixed(1) : 0,
        stakesWinners: grandTotalRow.StakesWinner || 0,
        stakesWinPct: grandTotalRow["%StksWnr"] != null ? +(grandTotalRow["%StksWnr"] * 100).toFixed(1) : 0,
        gradedStakesWinners: grandTotalRow.GrdStakesWinner || 0,
        g1Winners: grandTotalRow.G1Winner || 0,
      }
    : null;

  await writeFile(
    join(OUT_DIR, "vendors.json"),
    JSON.stringify({ vendors, grandTotal }, null, 0)
  );
  console.log(`vendors.json: ${vendors.length} vendors`);

  // 2. Parse "Sales" sheet → historic-sales-summary.json
  const salesSheet = workbook.Sheets["Sales"];
  const salesRaw = XLSX.utils.sheet_to_json(salesSheet);
  const sales = salesRaw.map((r) => ({
    sale: r.Sale,
    runners: r.Runner || 0,
    winners: r.Winner || 0,
    winPct: r["%Wnr"] != null ? +(r["%Wnr"] * 100).toFixed(1) : 0,
    stakesWinners: r.StakesWinner || 0,
    stakesWinPct: r["%StksWnr"] != null ? +(r["%StksWnr"] * 100).toFixed(1) : 0,
    gradedStakesWinners: r.GradedStksWinner || 0,
    gradedStakesPct: r["%GrdStks"] != null ? +(r["%GrdStks"] * 100).toFixed(1) : 0,
    g1Winners: r.Grade1Winner || 0,
    g1Pct: r["%G1"] != null ? +(r["%G1"] * 100).toFixed(1) : 0,
  }));

  await writeFile(
    join(OUT_DIR, "sales-summary.json"),
    JSON.stringify(sales, null, 0)
  );
  console.log(`sales-summary.json: ${sales.length} sales`);

  // 3. Parse "Data" sheet → vendor-data.json (individual horse records)
  const dataSheet = workbook.Sheets["Data"];
  const dataRaw = XLSX.utils.sheet_to_json(dataSheet);
  console.log(`Data sheet: ${dataRaw.length} rows`);

  // Map to compact records
  const records = dataRaw.map((r) => ({
    hip: r["Hip#"] || null,
    color: r.Color || null,
    sex: r.Sex || null,
    sire: r.Sire || null,
    dam: r.Dam || null,
    vendor: r.Vendor || null,
    price: r["Price "] || r["Price"] || null,
    sale: r.SaleName || null,
    year: r.Year || null,
    name: r.name || null,
    runner: r.Runner || 0,
    winner: r.Winner || 0,
    stakesWinner: r.StakesWinner || 0,
    gradedStakesWinner: r.GradedStakesWinner || 0,
    g1Winner: r.Grade1Winner || 0,
  }));

  await writeFile(
    join(OUT_DIR, "vendor-data.json"),
    JSON.stringify(records, null, 0)
  );
  console.log(`vendor-data.json: ${records.length} records`);

  // 4. Pre-aggregate vendor stats by sale for the "By Sale" view
  const vendorBySale = {};
  for (const r of records) {
    const saleKey = r.sale;
    if (!saleKey) continue;

    if (!vendorBySale[saleKey]) vendorBySale[saleKey] = {};
    if (!vendorBySale[saleKey][r.vendor]) {
      vendorBySale[saleKey][r.vendor] = {
        vendor: r.vendor,
        cataloged: 0,
        sold: 0,
        totalRevenue: 0,
        prices: [],
        runners: 0,
        winners: 0,
        stakesWinners: 0,
        gradedStakesWinners: 0,
        g1Winners: 0,
      };
    }

    const v = vendorBySale[saleKey][r.vendor];
    v.cataloged++;
    if (r.price && r.price > 0) {
      v.sold++;
      v.totalRevenue += r.price;
      v.prices.push(r.price);
    }
    if (r.runner) v.runners++;
    if (r.winner) v.winners++;
    if (r.stakesWinner) v.stakesWinners++;
    if (r.gradedStakesWinner) v.gradedStakesWinners++;
    if (r.g1Winner) v.g1Winners++;
  }

  // Convert to arrays and compute averages
  const vendorBySaleOut = {};
  for (const [sale, vendors] of Object.entries(vendorBySale)) {
    vendorBySaleOut[sale] = Object.values(vendors).map((v) => {
      const prices = v.prices;
      const sorted = [...prices].sort((a, b) => a - b);
      return {
        vendor: v.vendor,
        cataloged: v.cataloged,
        sold: v.sold,
        totalRevenue: v.totalRevenue,
        avgPrice: v.sold > 0 ? Math.round(v.totalRevenue / v.sold) : 0,
        medianPrice: sorted.length > 0 ? sorted[Math.floor(sorted.length / 2)] : 0,
        maxPrice: sorted.length > 0 ? sorted[sorted.length - 1] : 0,
        runners: v.runners,
        winners: v.winners,
        stakesWinners: v.stakesWinners,
        gradedStakesWinners: v.gradedStakesWinners,
        g1Winners: v.g1Winners,
      };
    });
  }

  await writeFile(
    join(OUT_DIR, "vendor-by-sale.json"),
    JSON.stringify(vendorBySaleOut, null, 0)
  );
  console.log(`vendor-by-sale.json: ${Object.keys(vendorBySaleOut).length} sales`);

  console.log("\nDone! All JSON files written to frontend/public/data/historic/");
}

main().catch(console.error);
