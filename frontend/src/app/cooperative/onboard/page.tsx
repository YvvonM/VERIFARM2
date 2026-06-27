"use client";

// Cooperative onboarding page: turn a CSV of member records into
// lender-accessible farmer profiles via POST /api/v1/cooperative/onboard.
//
// Expected CSV columns (header row required):
//   farmer_id, phone_number, land_size_hectares, production_volume_kg, crop_type
//
// Each row becomes one cooperative-attested PayloadBundle on submit — see
// app/api/cooperative.py for the backend contract this page calls.

import { useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

interface CsvRow {
  farmer_id: string;
  phone_number?: string;
  land_size_hectares?: string;
  production_volume_kg?: string;
  crop_type?: string;
}

interface OnboardSummary {
  institution_id: string;
  members_submitted: number;
  members_ingested: number;
  members_dlq: number;
  claims_written: number;
  members_eligible_for_match: string[];
}

function parseCsv(text: string): CsvRow[] {
  const lines = text.trim().split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const cells = line.split(",").map((c) => c.trim());
    const row: Record<string, string> = {};
    headers.forEach((h, i) => {
      row[h] = cells[i] ?? "";
    });
    return row as unknown as CsvRow;
  });
}

function rowsToMembers(rows: CsvRow[]) {
  return rows
    .filter((r) => r.farmer_id)
    .map((r) => {
      const claims: Record<string, unknown>[] = [];
      if (r.land_size_hectares) {
        claims.push({
          claim_type: "land_size_hectares",
          value_numeric: Number(r.land_size_hectares),
          unit: "ha",
          confidence: 0.75,
        });
      }
      if (r.production_volume_kg) {
        claims.push({
          claim_type: "production_volume_kg",
          value_numeric: Number(r.production_volume_kg),
          unit: "kg",
          confidence: 0.75,
        });
      }
      if (r.crop_type) {
        claims.push({
          claim_type: "crop_type",
          value_string: r.crop_type,
          confidence: 0.75,
        });
      }
      return {
        farmer_id: r.farmer_id,
        phone_number: r.phone_number || null,
        claims,
      };
    })
    .filter((m) => m.claims.length > 0);
}

export default function CooperativeOnboardPage() {
  const [institutionId, setInstitutionId] = useState("");
  const [institutionName, setInstitutionName] = useState("");
  const [rows, setRows] = useState<CsvRow[]>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [summary, setSummary] = useState<OnboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const preview = useMemo(() => rows.slice(0, 5), [rows]);

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setSummary(null);
    setError(null);
    const text = await file.text();
    setRows(parseCsv(text));
  };

  const onSubmit = async () => {
    if (!institutionId.trim() || !institutionName.trim()) {
      setError("Cooperative id and name are required.");
      return;
    }
    const members = rowsToMembers(rows);
    if (members.length === 0) {
      setError("No valid member rows to submit (need farmer_id + at least one claim column).");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (API_KEY) headers["X-API-Key"] = API_KEY;

      const res = await fetch(`${API_BASE}/api/v1/cooperative/onboard`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          institution_id: institutionId.trim(),
          institution_name: institutionName.trim(),
          members,
        }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status}: ${detail}`);
      }
      setSummary(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-semibold text-gray-900">Cooperative Onboarding</h1>
      <p className="mt-1 text-sm text-gray-600">
        Upload your member records (CSV). Each row becomes a verified, cooperative-attested
        claim — your farmers become eligible for lender review immediately, with no separate
        self-verification step.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Cooperative ID</span>
          <input
            type="text"
            value={institutionId}
            onChange={(e) => setInstitutionId(e.target.value)}
            placeholder="ORG-TEGEMEO"
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-green-600 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Cooperative Name</span>
          <input
            type="text"
            value={institutionName}
            onChange={(e) => setInstitutionName(e.target.value)}
            placeholder="Tegemeo Cereals Enterprises"
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-green-600 focus:outline-none"
          />
        </label>
      </div>

      <div className="mt-6">
        <span className="text-sm font-medium text-gray-700">Member CSV</span>
        <p className="mt-1 text-xs text-gray-500">
          Columns: farmer_id, phone_number, land_size_hectares, production_volume_kg, crop_type
        </p>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={onFileChange}
          className="mt-2 block text-sm text-gray-700"
        />
        {fileName ? <p className="mt-1 text-xs text-gray-500">{fileName} — {rows.length} row(s) parsed.</p> : null}
      </div>

      {preview.length > 0 ? (
        <div className="mt-6 overflow-x-auto rounded-md border border-gray-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50">
              <tr>
                {Object.keys(preview[0]).map((col) => (
                  <th key={col} className="px-3 py-2 font-medium text-gray-600">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.map((row, i) => (
                <tr key={i} className="border-t border-gray-100">
                  {Object.values(row).map((val, j) => (
                    <td key={j} className="px-3 py-2 text-gray-800">{String(val)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-gray-100 px-3 py-2 text-xs text-gray-500">
            Showing first {preview.length} of {rows.length} row(s).
          </p>
        </div>
      ) : null}

      <button
        type="button"
        onClick={onSubmit}
        disabled={submitting || rows.length === 0}
        className="mt-6 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {submitting ? "Submitting…" : "Submit to VeriFarm"}
      </button>

      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

      {summary ? (
        <div className="mt-6 rounded-lg border-l-4 border-green-600 bg-green-50 p-4">
          <h2 className="text-base font-semibold text-green-900">Onboarding complete</h2>
          <ul className="mt-2 space-y-1 text-sm text-green-900">
            <li>Members submitted: {summary.members_submitted}</li>
            <li>Members ingested: {summary.members_ingested}</li>
            <li>Members needing more data (sent to DLQ): {summary.members_dlq}</li>
            <li>Claims written: {summary.claims_written}</li>
            <li>Eligible for the MATCH engine: {summary.members_eligible_for_match.length}</li>
          </ul>
        </div>
      ) : null}
    </main>
  );
}
