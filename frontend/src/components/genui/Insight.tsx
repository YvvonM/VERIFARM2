// GenUI Insight — renders the backend `Insight` componentType: the copilot's
// synthesized, plain-language conclusion shown on top of chart/table data.
// Props contract (app/models/ui_schemas.py::InsightProps):
//   { text: string, title?: string | null }

import { Lightbulb } from "lucide-react";

export interface InsightComponentProps {
  text: string;
  title?: string | null;
}

export function Insight({ text, title }: InsightComponentProps) {
  return (
    <div className="flex items-start gap-3 rounded-lg border-l-4 border-green-600 bg-green-50 p-4">
      <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-green-700" aria-hidden="true" />
      <div>
        {title ? (
          <h3 className="mb-1 text-base font-semibold text-green-900">{title}</h3>
        ) : null}
        <p className="whitespace-pre-wrap text-base text-green-900">{text}</p>
      </div>
    </div>
  );
}

export default Insight;
