"use client";

// Dedicated detail page for one farmer -- reached by clicking a card in the
// dashboard list (app/page.tsx). Prefers the row sessionStorage handed off
// from the list (no extra fetch); falls back to fetching the eligible-
// farmers list and finding this id (covers a bookmarked/shared/refreshed
// link), and finally to a minimal placeholder if the farmer isn't in that
// list at all -- the page must never show a blank/broken state.
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { LenderNav } from "@/components/nav/LenderNav";
import { FarmerProfilePanel } from "@/components/lender/FarmerProfilePanel";
import { EligibleFarmer } from "@/components/lender/types";
import { SELECTED_FARMER_STORAGE_KEY } from "@/components/lender/selectedFarmerStorage";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return headers;
}

function placeholderFarmer(farmerId: string): EligibleFarmer {
  return {
    farmer_id: farmerId,
    cooperative_name: null,
    crop_types: [],
    verified_land_hectares: null,
    verification_sources: [],
    matched_products: [],
  };
}

export default function FarmerDetailPage() {
  const params = useParams<{ farmerId: string }>();
  const farmerId = decodeURIComponent(params.farmerId);

  const [farmer, setFarmer] = useState<EligibleFarmer | null>(null);
  const [region, setRegion] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    // 1. Try the handoff from the list page first -- no extra network call.
    try {
      const raw = sessionStorage.getItem(SELECTED_FARMER_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { farmer: EligibleFarmer; region: string };
        if (parsed.farmer?.farmer_id === farmerId) {
          setFarmer(parsed.farmer);
          setRegion(parsed.region ?? "");
          setLoading(false);
          return;
        }
      }
    } catch {
      // Fall through to the network fallback below.
    }

    // 2. Fallback: fetch the eligible-farmers list and find this id (covers
    // a bookmarked/shared/refreshed link with no sessionStorage handoff).
    fetch(`${API_BASE}/api/v1/lender/eligible-farmers?min_trust_score=0&page_size=100`, {
      headers: authHeaders(),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: { farmers: EligibleFarmer[] }) => {
        if (cancelled) return;
        const found = (data.farmers ?? []).find((f) => f.farmer_id === farmerId);
        setFarmer(found ?? placeholderFarmer(farmerId));
      })
      .catch(() => {
        if (!cancelled) setFarmer(placeholderFarmer(farmerId));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [farmerId]);

  return (
    <div className="flex h-screen flex-col bg-background">
      <LenderNav />
      <div className="border-b border-white/10 px-6 py-3">
        <Link
          href="/"
          className="flex items-center gap-1 text-sm text-white/60 hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Farmer Search
        </Link>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading || !farmer ? (
          <div className="flex h-full items-center justify-center text-sm text-white/40">
            Loading farmer profile…
          </div>
        ) : (
          <FarmerProfilePanel listFarmer={farmer} region={region} />
        )}
      </div>
    </div>
  );
}
