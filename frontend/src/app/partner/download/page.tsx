"use client";

// Data Download — same filters as Search. Since the export endpoints
// (GET /api/v1/export/claims, /claims.ndjson) only filter by claim_type/
// min_trust_score (no farmer demographics), this page gets its farmer-level
// filtering (crop type / region / min land hectares) by first asking the
// existing GET /api/v1/lender/eligible-farmers for the matching farmer_id
// set, then intersecting that with the exported claims client-side. Both
// calls are existing endpoints; no new backend filtering was added for this.
import { useEffect, useState } from "react";

import { PortalNav } from "@/components/nav/PortalNav";
import { friendlyClaimType } from "@/lib/claimLabels";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

interface ExportedClaim {
  claim_id: string | null;
  farmer_id: string;
  claim_type: string;
  value_numeric: number | null;
  value_string: string | null;
  unit: string | null;
  confidence: number | null;
  timestamp: string | null;
  attested_by_id: string | null;
  attested_by: string | null;
  attested_by_trust: number;
  authoritative: boolean;
}

interface Product {
  product_id: string;
  lender_name: string;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return headers;
}

function downloadBlob(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function toCsv(claims: ExportedClaim[]): string {
  const headers = [
    "claim_id", "farmer_id", "claim_type", "value_numeric", "value_string",
    "unit", "confidence", "timestamp", "attested_by", "attested_by_trust", "authoritative",
  ];
  const rows = claims.map((c) =>
    headers
      .map((h) => {
        const v = (c as unknown as Record<string, unknown>)[h];
        const s = v === null || v === undefined ? "" : String(v);
        return s.includes(",") ? `"${s.replace(/"/g, '""')}"` : s;
      })
      .join(","),
  );
  return [headers.join(","), ...rows].join("\n");
}

export default function PartnerDownloadPage() {
  const [cropType, setCropType] = useState("");
  const [region, setRegion] = useState("");
  const [minLandHectares, setMinLandHectares] = useState("");
  const [minTrustScore, setMinTrustScore] = useState(0.6);
  const [productId, setProductId] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [claims, setClaims] = useState<ExportedClaim[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/match/products`, { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : []))
      .then((p: Product[]) => setProducts(p))
      .catch(() => setProducts([]));
  }, []);

  const loadPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const farmerParams = new URLSearchParams();
      if (cropType) farmerParams.set("crop_type", cropType);
      if (region) farmerParams.set("region", region);
      if (minLandHectares) farmerParams.set("min_land_hectares", minLandHectares);
      if (productId) farmerParams.set("product_id", productId);
      farmerParams.set("min_trust_score", String(minTrustScore));
      farmerParams.set("page_size", "100");

      const farmersRes = await fetch(
        `${API_BASE}/api/v1/lender/eligible-farmers?${farmerParams}`,
        { headers: authHeaders() },
      );
      if (!farmersRes.ok) throw new Error(`${farmersRes.status}: ${await farmersRes.text()}`);
      const farmersData = await farmersRes.json();
      const allowedFarmerIds = new Set<string>(
        (farmersData.farmers ?? []).map((f: { farmer_id: string }) => f.farmer_id),
      );

      const claimsParams = new URLSearchParams();
      claimsParams.set("min_trust_score", String(minTrustScore));
      claimsParams.set("limit", "1000");
      const claimsRes = await fetch(`${API_BASE}/api/v1/export/claims?${claimsParams}`, {
        headers: authHeaders(),
      });
      if (!claimsRes.ok) throw new Error(`${claimsRes.status}: ${await claimsRes.text()}`);
      const claimsData = await claimsRes.json();

      const filtered: ExportedClaim[] = (claimsData.claims ?? []).filter((c: ExportedClaim) =>
        allowedFarmerIds.has(c.farmer_id),
      );
      setClaims(filtered);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  // Auto-load with the default filters on first visit, so there's always
  // something to see and download without needing to know to press a button
  // first.
  useEffect(() => {
    loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const downloadCsv = () => {
    downloadBlob(toCsv(claims), "verifarms_verified_claims.csv", "text/csv");
  };

  const downloadJson = () => {
    downloadBlob(JSON.stringify(claims, null, 2), "verifarms_verified_claims.json", "application/json");
  };

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <PortalNav />
      <h1 className="text-2xl font-semibold text-white">Get Farmer Data</h1>
      <p className="mt-1 text-sm text-white/60">
        Download information about farmers that match what you&apos;re looking for.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block">
          <span className="text-sm font-medium text-white/70">Crop type</span>
          <input
            value={cropType}
            onChange={(e) => setCropType(e.target.value)}
            placeholder="maize"
            className="mt-1 w-full rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-primary focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-white/70">Region</span>
          <input
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="Kirinyaga County"
            className="mt-1 w-full rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-primary focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-white/70">Min land (hectares)</span>
          <input
            type="number"
            min={0}
            step={0.1}
            value={minLandHectares}
            onChange={(e) => setMinLandHectares(e.target.value)}
            placeholder="1.0"
            className="mt-1 w-full rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-primary focus:outline-none"
          />
        </label>
        <label className="block sm:col-span-2">
          <span className="text-sm font-medium text-white/70">
            Minimum reliability: {Math.round(minTrustScore * 100)}%
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minTrustScore}
            onChange={(e) => setMinTrustScore(Number(e.target.value))}
            className="mt-2 w-full"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-white/70">Product</span>
          <select
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            className="mt-1 w-full rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-primary focus:outline-none"
          >
            <option value="">All products</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.product_id} — {p.lender_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={loadPreview}
          disabled={loading}
          className="rounded-md border border-white/15 px-4 py-2 text-sm font-medium text-white/70 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Show Results"}
        </button>
        <button
          type="button"
          onClick={downloadCsv}
          disabled={claims.length === 0}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          Download as Spreadsheet
        </button>
        <button
          type="button"
          onClick={downloadJson}
          disabled={claims.length === 0}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Download as Data File
        </button>
      </div>

      {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}

      {claims.length > 0 ? (
        <div className="mt-6 overflow-x-auto rounded-md border border-white/10">
          <p className="border-b border-white/10 px-3 py-2 text-xs text-white/40">
            {claims.length} matching record(s) — showing the first 10.
          </p>
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5">
              <tr>
                <th className="px-3 py-2 font-medium text-white/60">Farmer ID</th>
                <th className="px-3 py-2 font-medium text-white/60">What Was Checked</th>
                <th className="px-3 py-2 font-medium text-white/60">Value</th>
                <th className="px-3 py-2 font-medium text-white/60">How Sure</th>
                <th className="px-3 py-2 font-medium text-white/60">Checked By</th>
                <th className="px-3 py-2 font-medium text-white/60">Official Source</th>
              </tr>
            </thead>
            <tbody>
              {claims.slice(0, 10).map((c, i) => (
                <tr key={c.claim_id ?? i} className="border-t border-white/10">
                  <td className="px-3 py-2 text-white/80">{c.farmer_id}</td>
                  <td className="px-3 py-2 text-white/80">{friendlyClaimType(c.claim_type)}</td>
                  <td className="px-3 py-2 text-white/80">
                    {c.value_numeric ?? c.value_string ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-white/80">
                    {c.confidence != null ? `${(c.confidence * 100).toFixed(0)}%` : "—"}
                  </td>
                  <td className="px-3 py-2 text-white/80">{c.attested_by ?? "—"}</td>
                  <td className="px-3 py-2 text-white/80">{c.authoritative ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="mt-8 rounded-lg border-l-4 border-secondary bg-secondary/10 p-4 text-sm text-secondary">
        This download only includes information that has been checked and verified. Farmers&apos;
        original records are never shared. What you can do with this data is governed by your
        partner agreement.
      </div>
    </main>
  );
}
