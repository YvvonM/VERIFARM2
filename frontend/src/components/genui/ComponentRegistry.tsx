// Maps backend `componentType` strings to their React components. This is the
// single source of truth the page uses to turn a `component` SSE frame into UI;
// unknown types are handled gracefully by the caller.
import type { ComponentType } from "react";

import BarChartComponent from "./BarChartComponent";
import DataTable from "./DataTable";
import Insight from "./Insight";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const ComponentRegistry: Record<string, ComponentType<any>> = {
  BarChart: BarChartComponent,
  Table: DataTable,
  Insight,
};
