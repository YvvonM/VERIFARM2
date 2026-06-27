"use client";

// Partner Dashboard — landing page for the partner portal. Pulls portfolio
// numbers from the existing macro consumer endpoint
// (GET /api/v1/macro/cooperative/{institution_id}/stats) -- no new backend
// route. The "total cooperatives onboarded" figure is the count of demo
// cooperatives this dashboard is wired to poll (see COOPERATIVE_IDS below);
// there is no system-wide "all cooperatives" endpoint to sum across yet.
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
  const [apiKeyCopied, setApiKeyCopied] = useState(false);

  const DUMMY_API_KEY = "vf_demo_partner_key_8f3c1a2e9b";

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
  const avgTrust =
    stats.length > 0
      ? stats.reduce((sum, s) => sum + s.average_trust_score, 0) / stats.length
      : 0;

  const copyApiKey = async () => {
    await navigator.clipboard.writeText(DUMMY_API_KEY);
    setApiKeyCopied(true);
    setTimeout(() => setApiKeyCopied(false), 2000);
  };

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <PortalNav />
      <h1 className="text-2xl font-semibold text-white">Partner Dashboard</h1>
      <p className="mt-1 text-sm text-white/60">
        Portfolio overview across the cooperatives you have access to.
      </p>

      {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="Total verified farmers" value={loading ? "…" : String(totalFarmers)} />
        <StatCard label="Cooperatives onboarded" value={loading ? "…" : String(totalCooperatives)} />
        <StatCard
          label="Average trust score"
          value={loading ? "…" : avgTrust.toFixed(2)}
        />
      </div>

      <div className="mt-8 flex gap-3">
        <Link
          href="/partner/search"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        >
          Search Farmers
        </Link>
        <Link
          href="/partner/download"
          className="rounded-md border border-white/15 px-4 py-2 text-sm font-medium text-white/70"
        >
          Download Data
        </Link>
      </div>

      <div className="mt-10 rounded-lg border border-white/10 p-4">
        <h2 className="text-sm font-semibold text-white/70">Your API Key</h2>
        <p className="mt-1 text-xs text-white/40">
          Demo key — static for this walkthrough, not a real credential.
        </p>
        <div className="mt-2 flex items-center gap-2">
          <code className="flex-1 truncate rounded-md bg-white/10 px-3 py-2 text-xs text-white/80">
            {DUMMY_API_KEY}
          </code>
          <button
            type="button"
            onClick={copyApiKey}
            className="rounded-md border border-white/15 px-3 py-2 text-xs font-medium text-white/70 hover:border-primary hover:text-primary"
          >
            {apiKeyCopied ? "Copied!" : "Copy"}
          </button>
        </div>
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
