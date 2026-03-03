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
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">
        Breeze Time vs. Sale Price
      </h3>
      <p className="text-xs text-gray-400 mb-4">
        {primaryDistance} mile &middot; {data.length} observations
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            type="number"
            dataKey="time"
            name="Breeze Time"
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
            tickLine={false}
            label={{
              value: "Breeze Time (s)",
              position: "insideBottom",
              offset: -5,
              fill: "#9ca3af",
              fontSize: 11,
            }}
            domain={["dataMin - 0.2", "dataMax + 0.2"]}
          />
          <YAxis
            type="number"
            dataKey="price"
            name="Price"
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={{ stroke: "#e5e7eb" }}
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
              fill: "#9ca3af",
              fontSize: 11,
            }}
          />
          <ZAxis range={[30, 30]} />
          <Tooltip
            content={({ payload }) => {
              if (!payload || payload.length === 0) return null;
              const d = payload[0].payload;
              return (
                <div className="bg-white border border-gray-200 rounded-lg p-3 text-xs shadow-lg">
                  <p className="font-semibold text-brand-600 mb-1">
                    Hip #{d.hip}
                  </p>
                  <p className="text-gray-600">Sire: {d.sire}</p>
                  <p className="text-gray-600">
                    Time: {formatBreezeTime(d.time)}
                  </p>
                  <p className="text-gray-900 font-semibold">
                    {formatCurrency(d.price)}
                  </p>
                </div>
              );
            }}
          />
          <Scatter
            data={data}
            fill="#3b82f6"
            fillOpacity={0.5}
            strokeWidth={0}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
