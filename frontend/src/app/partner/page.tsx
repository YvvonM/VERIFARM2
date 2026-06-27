"use client";

// Partner Dashboard — landing page for the partner portal. Pulls portfolio
// numbers from the existing macro consumer endpoint
// (GET /api/v1/macro/cooperative/{institution_id}/stats) -- no new backend
// route. The "cooperatives connected" figure is the count of demo
// cooperatives this dashboard is wired to poll (see COOPERATIVE_IDS below);
// there is no system-wide "all cooperatives" endpoint to sum across yet.
//
// Written for non-technical users: no API keys or technical terms shown
// here. "Reliability" is plain language for what the rest of the codebase
// calls trust_score.
import { useEffect, useState } from "react";
import Link from "next/link";

import { PortalNav } from "@/components/nav/PortalNav";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

// Demo cooperative ids this dashboard aggregates. In production this would
// come from a cooperative directory endpoint; none exists yet in this API.
const COOPERATIVE_IDS = ["ORG-TEGEMEO", "ORG-AGROVESTO"];

interface CooperativeStats {
  institution_id: string;
  total_members: number;
  total_verified_hectares: number;
  unverified_members: number;
  missing_credit_history_count: number;
  average_trust_score: number;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return headers;
}

export default function PartnerDashboardPage() {
  const [stats, setStats] = useState<CooperativeStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const results = await Promise.all(
          COOPERATIVE_IDS.map(async (id) => {
            const res = await fetch(
              `${API_BASE}/api/v1/macro/cooperative/${id}/stats`,
              { headers: authHeaders() },
            );
            if (!res.ok) return null;
            return (await res.json()) as CooperativeStats;
          }),
        );
        if (!cancelled) {
          setStats(results.filter((r): r is CooperativeStats => r !== null));
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const totalFarmers = stats.reduce((sum, s) => sum + s.total_members, 0);
  const totalCooperatives = stats.length;
  const avgReliabilityPct =
    stats.length > 0
      ? Math.round((stats.reduce((sum, s) => sum + s.average_trust_score, 0) / stats.length) * 100)
      : 0;

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <PortalNav />
      <h1 className="text-2xl font-semibold text-white">Your Farmers, At a Glance</h1>
      <p className="mt-1 text-sm text-white/60">
        A quick look at the farmers you can see and reach out to.
      </p>

      {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="Verified farmers" value={loading ? "…" : String(totalFarmers)} />
        <StatCard label="Cooperatives connected" value={loading ? "…" : String(totalCooperatives)} />
        <StatCard
          label="How reliable, on average"
          value={loading ? "…" : `${avgReliabilityPct}%`}
        />
      </div>

      <div className="mt-8 flex gap-3">
        <Link
          href="/partner/search"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        >
          Find Farmers
        </Link>
        <Link
          href="/partner/download"
          className="rounded-md border border-white/15 px-4 py-2 text-sm font-medium text-white/70"
        >
          Get Their Data
        </Link>
      </div>
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-white/40">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
    </div>
  );
}
