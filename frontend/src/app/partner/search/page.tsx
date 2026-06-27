"use client";

// Farmer Search — calls the existing GET /api/v1/lender/eligible-farmers
// (filterable, paginated, privacy-safe) and, per row, GET
// /api/v1/loan-officer/farmer/{farmer_id} for the "View Profile" modal.
//
// Privacy: the eligible-farmers rows never carry phone_number at all (see
// app/api/lender.py). The profile modal's API response DOES include
// phone_number (FarmerProfileResponse) -- we deliberately never read or
// render that field here, so farmer_id and phone never appear together
// in this UI.
import { useEffect, useState } from "react";

import { PortalNav } from "@/components/nav/PortalNav";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

interface MatchedProduct {
  product_id: string;
  lender_name: string;
  eligible: boolean;
}

interface EligibleFarmer {
  farmer_id: string;
  cooperative_name: string | null;
  crop_types: string[];
  verified_land_hectares: number | null;
  verification_sources: { source_trust: number }[];
  matched_products: MatchedProduct[];
}

interface ClaimDetail {
  value_numeric: number | null;
  confidence: number;
  source_name: string | null;
  is_authoritative: boolean;
  reputation_score: number | null;
}

interface FarmerProfile {
  farmer_id: string;
  // phone_number deliberately NOT declared here -- see file header.
  verified_history: Record<string, ClaimDetail[]>;
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

function topTrust(f: EligibleFarmer): number {
  return f.verification_sources.length > 0
    ? Math.max(...f.verification_sources.map((s) => s.source_trust))
    : 0;
}

export default function PartnerSearchPage() {
  const [cropType, setCropType] = useState("");
  const [region, setRegion] = useState("");
  const [minLandHectares, setMinLandHectares] = useState("");
  const [minTrustScore, setMinTrustScore] = useState(0.6);
  const [productId, setProductId] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [results, setResults] = useState<EligibleFarmer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [modalFarmerId, setModalFarmerId] = useState<string | null>(null);
  const [modalProfile, setModalProfile] = useState<FarmerProfile | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/match/products`, { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : []))
      .then((p: Product[]) => setProducts(p))
      .catch(() => setProducts([]));
  }, []);

  const search = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (cropType) params.set("crop_type", cropType);
      if (region) params.set("region", region);
      if (minLandHectares) params.set("min_land_hectares", minLandHectares);
      if (productId) params.set("product_id", productId);
      params.set("min_trust_score", String(minTrustScore));
      params.set("page_size", "50");

      const res = await fetch(`${API_BASE}/api/v1/lender/eligible-farmers?${params}`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
      const data = await res.json();
      setResults(data.farmers ?? []);
      setTotal(data.total ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const viewProfile = async (farmerId: string) => {
    setModalFarmerId(farmerId);
    setModalProfile(null);
    setModalError(null);
    setModalLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/loan-officer/farmer/${farmerId}`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
      const data = await res.json();
      // Explicitly drop phone_number even if the API includes it -- never
      // rendered alongside farmer_id in this UI.
      const { phone_number: _phone, ...safe } = data;
      void _phone;
      setModalProfile(safe as FarmerProfile);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : String(err));
    } finally {
      setModalLoading(false);
    }
  };

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <PortalNav />
      <h1 className="text-2xl font-semibold text-white">Farmer Search</h1>
      <p className="mt-1 text-sm text-white/60">
        Find verified farmers eligible for your financial products.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block">
          <span className="text-sm font-medium text-white/70">Crop type</span>
          <input
            value={cropType}
            onChange={(e) => setCropType(e.target.value)}
            placeholder="maize"
            className="mt-1 w-full rounded-md border border-white/15 px-3 py-2 text-sm focus:border-primary focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-white/70">Region</span>
          <input
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="Kirinyaga County"
            className="mt-1 w-full rounded-md border border-white/15 px-3 py-2 text-sm focus:border-primary focus:outline-none"
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
            className="mt-1 w-full rounded-md border border-white/15 px-3 py-2 text-sm focus:border-primary focus:outline-none"
          />
        </label>
        <label className="block sm:col-span-2">
          <span className="text-sm font-medium text-white/70">
            Min trust score: {minTrustScore.toFixed(2)}
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
            className="mt-1 w-full rounded-md border border-white/15 px-3 py-2 text-sm focus:border-primary focus:outline-none"
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

      <button
        type="button"
        onClick={search}
        disabled={loading}
        className="mt-6 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
      >
        {loading ? "Searching…" : "Search"}
      </button>

      {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}

      {results.length > 0 ? (
        <div className="mt-6 overflow-x-auto rounded-md border border-white/10">
          <p className="border-b border-white/10 px-3 py-2 text-xs text-white/40">
            {total} farmer(s) found.
          </p>
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5">
              <tr>
                <th className="px-3 py-2 font-medium text-white/60">Farmer ID</th>
                <th className="px-3 py-2 font-medium text-white/60">Cooperative</th>
                <th className="px-3 py-2 font-medium text-white/60">Crops</th>
                <th className="px-3 py-2 font-medium text-white/60">Verified land (ha)</th>
                <th className="px-3 py-2 font-medium text-white/60">Trust score</th>
                <th className="px-3 py-2 font-medium text-white/60">Matched products</th>
                <th className="px-3 py-2 font-medium text-white/60" />
              </tr>
            </thead>
            <tbody>
              {results.map((f) => (
                <tr key={f.farmer_id} className="border-t border-white/10">
                  <td className="px-3 py-2 text-white/80">{f.farmer_id}</td>
                  <td className="px-3 py-2 text-white/80">{f.cooperative_name ?? "—"}</td>
                  <td className="px-3 py-2 text-white/80">{f.crop_types.join(", ") || "—"}</td>
                  <td className="px-3 py-2 text-white/80">
                    {f.verified_land_hectares?.toFixed(2) ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-white/80">{topTrust(f).toFixed(2)}</td>
                  <td className="px-3 py-2 text-white/80">
                    {f.matched_products.filter((p) => p.eligible).map((p) => p.product_id).join(", ") || "—"}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => viewProfile(f.farmer_id)}
                      className="rounded-md border border-white/15 px-2 py-1 text-xs font-medium text-white/70 hover:border-primary hover:text-primary"
                    >
                      View Profile
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {modalFarmerId ? (
        <div
          className="fixed inset-0 flex items-center justify-center bg-black/40 p-6"
          onClick={() => setModalFarmerId(null)}
        >
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white/5 p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <h2 className="text-lg font-semibold text-white">
                Verified history — {modalFarmerId}
              </h2>
              <button
                type="button"
                onClick={() => setModalFarmerId(null)}
                className="text-white/30 hover:text-white/60"
              >
                ✕
              </button>
            </div>

            {modalLoading ? <p className="mt-4 text-sm text-white/40">Loading…</p> : null}
            {modalError ? <p className="mt-4 text-sm text-destructive">{modalError}</p> : null}

            {modalProfile ? (
              <div className="mt-4 space-y-4">
                {Object.entries(modalProfile.verified_history).map(([claimType, claims]) => (
                  <div key={claimType}>
                    <h3 className="text-sm font-semibold text-white/80">{claimType}</h3>
                    <ul className="mt-1 space-y-1">
                      {claims.map((c, i) => (
                        <li key={i} className="text-xs text-white/60">
                          {c.value_numeric ?? "—"} — {c.source_name ?? "unknown source"}
                          {c.is_authoritative ? " (authoritative)" : ""} — confidence{" "}
                          {(c.confidence * 100).toFixed(0)}%
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
                {Object.keys(modalProfile.verified_history).length === 0 ? (
                  <p className="text-sm text-white/40">No verified claims yet.</p>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </main>
  );
}
