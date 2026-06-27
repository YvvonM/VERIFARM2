"use client";

// Right panel: detail view for the farmer selected in FarmerSearchPanel.
// `listFarmer` is the row already fetched from /lender/eligible-farmers (it
// carries cooperative_name, crop_types, matched_products -- none of which the
// /loan-officer/farmer/{id} endpoint returns); `verified_history` (land size,
// production, identity, trust ring) comes from that loan-officer endpoint.
// Combining the two real responses avoids inventing any field or requiring a
// backend change.
import { useEffect, useState, type ReactNode } from "react";
import { Building2, MapPin, Satellite, ShieldCheck, Sprout } from "lucide-react";

import { AskAiBox } from "./AskAiBox";
import { ClaimDetail, EligibleFarmer, FarmerProfileResponse, trustColor } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return headers;
}

function bestClaim(history: Record<string, ClaimDetail[]>, claimType: string): ClaimDetail | null {
  const list = history[claimType];
  return list && list.length > 0 ? list[0] : null;
}

function sourceIcon(sourceName: string | undefined) {
  if (!sourceName) return <ShieldCheck className="h-4 w-4 text-gray-400" />;
  return /sentinel|satellite/i.test(sourceName) ? (
    <Satellite className="h-4 w-4 text-blue-400" />
  ) : (
    <Building2 className="h-4 w-4 text-amber-400" />
  );
}

function downloadCsv(farmerId: string, history: Record<string, ClaimDetail[]>) {
  const headers = ["claim_type", "value_numeric", "confidence", "source_name", "is_authoritative", "reputation_score"];
  const rows: string[] = [headers.join(",")];
  for (const [claimType, claims] of Object.entries(history)) {
    for (const c of claims) {
      rows.push(
        [
          claimType,
          c.value_numeric ?? "",
          c.confidence,
          c.source_name,
          c.is_authoritative,
          c.reputation_score ?? "",
        ]
          .map((v) => String(v))
          .join(","),
      );
    }
  }
  const blob = new Blob([rows.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${farmerId}_verified_claims.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

interface Props {
  listFarmer: EligibleFarmer;
  region: string;
}

export function FarmerProfilePanel({ listFarmer, region }: Props) {
  const [history, setHistory] = useState<Record<string, ClaimDetail[]>>({});
  const [loading, setLoading] = useState(true);
  const [usedFallback, setUsedFallback] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setUsedFallback(false);
    fetch(`${API_BASE}/api/v1/loan-officer/farmer/${listFarmer.farmer_id}`, {
      headers: authHeaders(),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: FarmerProfileResponse) => {
        if (!cancelled) setHistory(data.verified_history ?? {});
      })
      .catch(() => {
        if (!cancelled) {
          // Fallback: derive a minimal history from the search row so the
          // panel never shows a blank/broken state.
          setHistory({
            land_size_hectares: listFarmer.verified_land_hectares
              ? [
                  {
                    value_numeric: listFarmer.verified_land_hectares,
                    confidence: 0.8,
                    source_name: listFarmer.cooperative_name ?? "Unknown source",
                    is_authoritative: false,
                    reputation_score: null,
                  },
                ]
              : [],
          });
          setUsedFallback(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [listFarmer]);

  const land = bestClaim(history, "land_size_hectares");
  const production =
    bestClaim(history, "production_volume_kg") ?? bestClaim(history, "production_volume");
  const identity = bestClaim(history, "identity") ?? bestClaim(history, "identity_verified");

  const trustScore =
    Math.max(0, ...Object.values(history).flatMap((claims) => claims.map((c) => c.reputation_score ?? 0))) ||
    Math.max(0, ...listFarmer.verification_sources.map((s) => s.source_trust));
  const colors = trustColor(trustScore);
  const ringPct = Math.round(trustScore * 100);

  const eligibleProducts = listFarmer.matched_products.filter((p) => p.eligible);

  const farmerProfileForAi = {
    farmer_id: listFarmer.farmer_id,
    cooperative_name: listFarmer.cooperative_name,
    region: region || "unknown",
    crop_types: listFarmer.crop_types,
    trust_score: trustScore,
    verified_history: history,
    matched_products: listFarmer.matched_products,
  };

  return (
    <div className="h-full overflow-y-auto bg-background p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl uppercase tracking-wide text-white">
            {listFarmer.farmer_id}
          </h2>
          <div className="mt-1 flex flex-wrap items-center gap-4 text-sm text-white/60">
            <span className="flex items-center gap-1">
              <Building2 className="h-4 w-4" /> {listFarmer.cooperative_name ?? "Independent"}
            </span>
            <span className="flex items-center gap-1">
              <MapPin className="h-4 w-4" /> {region || "Region unknown"}
            </span>
            <span className="flex items-center gap-1">
              <Sprout className="h-4 w-4" /> {listFarmer.crop_types.join(", ") || "Unknown crop"}
            </span>
          </div>
        </div>

        {/* Trust score ring */}
        <div className="relative flex h-20 w-20 items-center justify-center">
          <svg viewBox="0 0 36 36" className="h-20 w-20 -rotate-90">
            <circle cx="18" cy="18" r="16" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="3" />
            <circle
              cx="18"
              cy="18"
              r="16"
              fill="none"
              stroke={colors.ring}
              strokeWidth="3"
              strokeDasharray={`${ringPct} ${100 - ringPct}`}
              strokeLinecap="round"
            />
          </svg>
          <span className={`absolute text-lg font-bold ${colors.text}`}>{trustScore.toFixed(2)}</span>
        </div>
      </div>

      {usedFallback ? (
        <p className="mt-2 text-xs text-secondary">
          Verified-history lookup failed — showing limited data from the search result.
        </p>
      ) : null}

      {loading ? <p className="mt-6 text-sm text-white/40">Loading profile…</p> : null}

      {/* Verification strip */}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <VerificationBox
          icon={<Satellite className="h-5 w-5 text-blue-400" />}
          label="Land Size"
          value={land ? `${land.value_numeric} ha` : "No verified claim"}
          source={land?.source_name}
          sourceIcon={sourceIcon(land?.source_name)}
          confidence={land?.confidence}
        />
        <VerificationBox
          icon={<Sprout className="h-5 w-5 text-amber-400" />}
          label="Production Volume"
          value={production ? `${production.value_numeric} kg` : "No verified claim"}
          source={production?.source_name}
          sourceIcon={sourceIcon(production?.source_name)}
          confidence={production?.confidence}
        />
        <VerificationBox
          icon={<ShieldCheck className="h-5 w-5 text-green-400" />}
          label="Identity Status"
          value={identity ? "Verified" : "Unverified"}
          source={identity?.source_name}
          sourceIcon={sourceIcon(identity?.source_name)}
          confidence={identity?.confidence}
        />
      </div>

      {/* Matched products */}
      <div className="mt-8">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-white/70">Matched Products</h3>
        {eligibleProducts.length === 0 ? (
          <p className="mt-2 text-sm text-white/40">No products currently matched.</p>
        ) : (
          <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {eligibleProducts.map((p) => (
              <div key={p.product_id} className="rounded-xl border border-primary/20 bg-primary/10 p-3">
                <p className="text-sm font-semibold text-primary">{p.product_id}</p>
                <p className="text-xs text-primary/70">{p.lender_name}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={() => downloadCsv(listFarmer.farmer_id, history)}
        className="mt-6 rounded-md border border-white/15 px-4 py-2 text-sm font-medium text-white/70 hover:border-primary hover:text-primary"
      >
        Download Profile (CSV)
      </button>

      <AskAiBox farmerProfile={farmerProfileForAi} />
    </div>
  );
}

function VerificationBox({
  icon,
  label,
  value,
  source,
  sourceIcon,
  confidence,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  source?: string;
  sourceIcon: ReactNode;
  confidence?: number;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-white/50">
        {icon} {label}
      </div>
      <p className="mt-2 text-lg font-semibold text-white">{value}</p>
      <div className="mt-2 flex items-center justify-between text-xs text-white/50">
        <span className="flex items-center gap-1">
          {sourceIcon} {source ?? "—"}
        </span>
        {confidence != null ? <span>{Math.round(confidence * 100)}%</span> : null}
      </div>
    </div>
  );
}

export default FarmerProfilePanel;
