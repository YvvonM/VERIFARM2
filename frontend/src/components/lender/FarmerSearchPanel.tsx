"use client";

// Left panel: search + filters over GET /api/v1/lender/eligible-farmers.
// Free-text search and the Region dropdown filter client-side over the
// already-fetched list, because (a) the endpoint has no free-text farmer_id
// search param, and (b) EligibleFarmer rows don't echo back a per-farmer
// region (the backend filters by region server-side but doesn't return it --
// see app/api/lender.py). When a region filter IS active, every returned row
// matches it by construction, so it's accurate to display; with no region
// filter active, region is shown as "--" rather than guessed.
import { useEffect, useState } from "react";

import { EligibleFarmer, topTrustScore, trustColor } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

const TRUST_LEVELS: Record<string, number> = { Low: 0.4, Medium: 0.6, High: 0.8 };

// Hardcoded fallback so the page is never empty if the API call fails.
const FALLBACK_FARMERS: EligibleFarmer[] = [
  { farmer_id: "F-0001", cooperative_name: "Tegemeo Cereals Enterprises", crop_types: ["maize"], verified_land_hectares: 2.4, verification_sources: [{ claim_type: "land_size_hectares", value: "2.4", source: "Sentinel-2", source_trust: 1.0 }], matched_products: [] },
  { farmer_id: "F-0002", cooperative_name: "Kirinyaga Farmers Cooperative", crop_types: ["tea"], verified_land_hectares: 1.8, verification_sources: [{ claim_type: "land_size_hectares", value: "1.8", source: "Sentinel-2", source_trust: 1.0 }], matched_products: [] },
  { farmer_id: "F-0003", cooperative_name: "Agrovesto Cooperative", crop_types: ["cassava"], verified_land_hectares: 3.1, verification_sources: [{ claim_type: "land_size_hectares", value: "3.1", source: "ORG-AGROVESTO", source_trust: 0.55 }], matched_products: [] },
  { farmer_id: "F-0004", cooperative_name: "Tegemeo Cereals Enterprises", crop_types: ["beans"], verified_land_hectares: 0.9, verification_sources: [{ claim_type: "land_size_hectares", value: "0.9", source: "ORG-TEGEMEO", source_trust: 0.53 }], matched_products: [] },
  { farmer_id: "F-0005", cooperative_name: "Kirinyaga SACCO", crop_types: ["maize"], verified_land_hectares: 4.6, verification_sources: [{ claim_type: "land_size_hectares", value: "4.6", source: "Sentinel-2", source_trust: 1.0 }], matched_products: [] },
];

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return headers;
}

interface Props {
  selectedFarmerId: string | null;
  onSelect: (farmer: EligibleFarmer, region: string) => void;
}

export function FarmerSearchPanel({ selectedFarmerId, onSelect }: Props) {
  const [searchText, setSearchText] = useState("");
  const [cropType, setCropType] = useState("");
  const [region, setRegion] = useState("");
  const [trustLevel, setTrustLevel] = useState("");
  const [farmers, setFarmers] = useState<EligibleFarmer[]>([]);
  const [usedFallback, setUsedFallback] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (cropType) params.set("crop_type", cropType);
      if (region) params.set("region", region);
      params.set("min_trust_score", String(TRUST_LEVELS[trustLevel] ?? 0.5));
      params.set("page_size", "50");

      const res = await fetch(`${API_BASE}/api/v1/lender/eligible-farmers?${params}`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      const list: EligibleFarmer[] = data.farmers ?? [];
      setFarmers(list);
      setUsedFallback(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setFarmers(FALLBACK_FARMERS);
      setUsedFallback(true);
    } finally {
      setLoading(false);
    }
  };

  // Auto-populate on mount with default filters.
  useEffect(() => {
    runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visible = farmers.filter((f) => {
    if (!searchText.trim()) return true;
    const q = searchText.trim().toLowerCase();
    return (
      f.farmer_id.toLowerCase().includes(q) ||
      f.crop_types.some((c) => c.toLowerCase().includes(q)) ||
      (region && region.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex h-full flex-col border-r border-white/10 bg-white/5">
      <div className="space-y-3 border-b border-white/10 p-4">
        <input
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          placeholder="Search by farmer ID, region, or crop"
          className="w-full rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-primary focus:outline-none"
        />
        <div className="grid grid-cols-1 gap-2">
          <select
            value={cropType}
            onChange={(e) => setCropType(e.target.value)}
            className="w-full rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-sm text-white"
          >
            <option className="text-black" value="">Any crop</option>
            <option className="text-black" value="maize">Maize</option>
            <option className="text-black" value="tea">Tea</option>
            <option className="text-black" value="beans">Beans</option>
            <option className="text-black" value="cassava">Cassava</option>
            <option className="text-black" value="rice">Rice</option>
          </select>
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="w-full rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-sm text-white"
          >
            <option className="text-black" value="">Any region</option>
            <option className="text-black" value="Kirinyaga County">Kirinyaga County</option>
            <option className="text-black" value="Oyo State">Oyo State</option>
          </select>
          <select
            value={trustLevel}
            onChange={(e) => setTrustLevel(e.target.value)}
            className="w-full rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-sm text-white"
          >
            <option className="text-black" value="">Min trust score: Any</option>
            <option className="text-black" value="Low">Min trust score: Low (0.4)</option>
            <option className="text-black" value="Medium">Min trust score: Medium (0.6)</option>
            <option className="text-black" value="High">Min trust score: High (0.8)</option>
          </select>
        </div>
        <button
          type="button"
          onClick={runSearch}
          disabled={loading}
          className="w-full rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {loading ? "Searching…" : "Search"}
        </button>
        {usedFallback ? (
          <p className="text-xs text-secondary">
            Live search failed ({error}) — showing sample farmers.
          </p>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {visible.length === 0 ? (
          <p className="p-4 text-sm text-white/40">No farmers match these filters.</p>
        ) : (
          <ul className="space-y-2">
            {visible.map((f) => {
              const trust = topTrustScore(f);
              const colors = trustColor(trust);
              const active = f.farmer_id === selectedFarmerId;
              return (
                <li key={f.farmer_id}>
                  <button
                    type="button"
                    onClick={() => onSelect(f, region)}
                    className={`w-full rounded-md border p-3 text-left transition ${
                      active
                        ? "border-primary bg-primary/10"
                        : "border-white/10 bg-white/5 hover:border-primary/50"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-white">{f.farmer_id}</span>
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors.badge}`}>
                        {trust.toFixed(2)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-white/50">
                      {f.crop_types.join(", ") || "Unknown crop"} ·{" "}
                      {region || "Region unknown"}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

export default FarmerSearchPanel;
