"use client";

// GenUI BarChart — renders the backend `BarChart` componentType.
// Props contract (app/models/ui_schemas.py::BarChartProps):
//   { data: Array<Record<string, unknown>>, xKey: string, yKey: string }
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface BarChartComponentProps {
  data: Array<Record<string, unknown>>;
  xKey: string;
  yKey: string;
}

export function BarChartComponent({ data, xKey, yKey }: BarChartComponentProps) {
  if (!Array.isArray(data) || data.length === 0) {
    return <p className="text-sm text-gray-400">No data to chart.</p>;
  }
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} allowDecimals />
          <Tooltip />
          <Bar dataKey={yKey} fill="#16a34a" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default BarChartComponent;
