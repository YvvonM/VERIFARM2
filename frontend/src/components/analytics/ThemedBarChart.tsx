"use client";

// Shared dark-theme bar chart for the Analytics page. Same recharts
// dependency as components/genui/BarChartComponent.tsx, just themed for the
// dark-green palette instead of light Tailwind defaults.
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ThemedBarChartProps {
  data: Array<Record<string, unknown>>;
  xKey: string;
  yKey: string;
  color?: string;
  height?: number;
}

export function ThemedBarChart({ data, xKey, yKey, color = "#4ade80", height = 260 }: ThemedBarChartProps) {
  if (!Array.isArray(data) || data.length === 0) {
    return <p className="text-sm text-white/40">No data to chart.</p>;
  }
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
          <XAxis dataKey={xKey} tick={{ fontSize: 11, fill: "rgba(255,255,255,0.6)" }} />
          <YAxis tick={{ fontSize: 11, fill: "rgba(255,255,255,0.6)" }} allowDecimals={false} />
          <Tooltip
            contentStyle={{
              background: "#0b1f16",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              fontSize: 12,
              color: "#fff",
            }}
          />
          <Bar dataKey={yKey} fill={color} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default ThemedBarChart;
