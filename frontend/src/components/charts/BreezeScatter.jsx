import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
} from "recharts";
import { formatCurrency, formatBreezeTime } from "../../lib/format";

export default function BreezeScatter({ breezeByDistance }) {
  if (!breezeByDistance) return null;

  const distances = Object.keys(breezeByDistance);
  if (distances.length === 0) return null;

  // Use the first distance with data
  const primaryDistance = distances[0];
  const data = breezeByDistance[primaryDistance]
    .filter((d) => d.price != null)
    .map((d) => ({
      time: d.time,
      price: d.price,
      hip: d.hip,
      sire: d.sire,
    }));

  if (data.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
      <h3 className="text-sm font-semibold text-white mb-1">
        Breeze Time vs. Sale Price
      </h3>
      <p className="text-xs text-slate-500 mb-4">
        {primaryDistance} mile &middot; {data.length} observations
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            type="number"
            dataKey="time"
            name="Breeze Time"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
            label={{
              value: "Breeze Time (s)",
              position: "insideBottom",
              offset: -5,
              fill: "#64748b",
              fontSize: 11,
            }}
            domain={["dataMin - 0.2", "dataMax + 0.2"]}
          />
          <YAxis
            type="number"
            dataKey="price"
            name="Price"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
            tickFormatter={(v) =>
              v >= 1000000
                ? `$${(v / 1000000).toFixed(1)}M`
                : `$${(v / 1000).toFixed(0)}K`
            }
            label={{
              value: "Sale Price (USD)",
              angle: -90,
              position: "insideLeft",
              fill: "#64748b",
              fontSize: 11,
            }}
          />
          <ZAxis range={[30, 30]} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value, name) => {
              if (name === "Price") return formatCurrency(value);
              if (name === "Breeze Time") return formatBreezeTime(value);
              return value;
            }}
            labelFormatter={() => ""}
            content={({ payload }) => {
              if (!payload || payload.length === 0) return null;
              const d = payload[0].payload;
              return (
                <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 text-xs shadow-xl">
                  <p className="font-semibold text-brand-400 mb-1">
                    Hip #{d.hip}
                  </p>
                  <p className="text-slate-300">Sire: {d.sire}</p>
                  <p className="text-slate-300">
                    Time: {formatBreezeTime(d.time)}
                  </p>
                  <p className="text-white font-semibold">
                    {formatCurrency(d.price)}
                  </p>
                </div>
              );
            }}
          />
          <Scatter
            data={data}
            fill="#3391ff"
            fillOpacity={0.6}
            strokeWidth={0}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
