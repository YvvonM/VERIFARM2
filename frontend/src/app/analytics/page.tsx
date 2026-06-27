"use client";

// Analytics — value-chain charts for a lender, not a single-farmer drill-down
// (that's the home dashboard) and not a cooperative's own portfolio view
// (that's /partner, left untouched). Every chart here is backed by a fixed,
// hand-written Cypher query (app/api/analytics.py) -- deliberately NOT the
// LLM-driven Cypher agent, whose schema description has drifted from the
// reified model and produces unreliable queries. Deliberately no trust-score
// distribution chart, per direction.
import { useEffect, useState, type ReactNode } from "react";

import { PortalNav } from "@/components/nav/PortalNav";
import { ThemedBarChart } from "@/components/analytics/ThemedBarChart";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return headers;
}

interface OrganizationFarmerCount {
  organization: string;
  org_role: string | null;
  farmer_count: number;
}
interface CropFarmerCount {
  crop_type: string;
  farmer_count: number;
}
interface OrganizationLandSize {
  organization: string;
  avg_hectares: number;
  total_hectares: number;
  farmer_count: number;
}
interface CropProduction {
  crop_type: string;
  total_kg: number;
  farmer_count: number;
}
interface ProductEligibility {
  product_id: string;
  lender_name: string;
  eligible_count: number;
  total_farmers: number;
}

function useAnalytics<T>(endpoint: string) {
  const [data, setData] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE}/api/v1/analytics/${endpoint}`, { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((json: T[]) => {
        if (!cancelled) setData(json);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint]);

  return { data, loading, error };
}

function ChartCard({
  title,
  subtitle,
  loading,
  error,
  children,
}: {
  title: string;
  subtitle: string;
  loading: boolean;
  error: string | null;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5">
      <h2 className="font-display text-base uppercase tracking-wide text-white">{title}</h2>
      <p className="mt-1 text-xs text-white/40">{subtitle}</p>
      <div className="mt-4">
        {loading ? (
          <p className="text-sm text-white/40">Loading…</p>
        ) : error ? (
          <p className="text-sm text-destructive">Failed to load ({error}).</p>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const orgFarmers = useAnalytics<OrganizationFarmerCount>("farmers-by-organization");
  const cropFarmers = useAnalytics<CropFarmerCount>("crop-distribution");
  const orgLand = useAnalytics<OrganizationLandSize>("land-size-by-organization");
  const cropProduction = useAnalytics<CropProduction>("production-by-crop");
  const eligibility = useAnalytics<ProductEligibility>("eligibility-by-product");

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <PortalNav />
      <h1 className="font-display text-2xl uppercase tracking-wide text-white">
        Portfolio Analytics
      </h1>
      <p className="mt-1 text-sm text-white/60">
        Value-chain view across partner organizations, crops, and products — not a single
        farmer&apos;s profile (see Farmer Search) and not one cooperative&apos;s own portfolio
        (see Partner Portal).
      </p>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ChartCard
          title="Verified Farmers by Partner Organization"
          subtitle="Where the verified farmer pool sits across cooperatives, off-takers, lenders, and mobile-money providers."
          loading={orgFarmers.loading}
          error={orgFarmers.error}
        >
          <ThemedBarChart
            data={orgFarmers.data as unknown as Record<string, unknown>[]}
            xKey="organization"
            yKey="farmer_count"
          />
        </ChartCard>

        <ChartCard
          title="Crop Distribution"
          subtitle="What the verified farmer pool is growing — portfolio diversification."
          loading={cropFarmers.loading}
          error={cropFarmers.error}
        >
          <ThemedBarChart
            data={cropFarmers.data as unknown as Record<string, unknown>[]}
            xKey="crop_type"
            yKey="farmer_count"
            color="#f4a261"
          />
        </ChartCard>

        <ChartCard
          title="Verified Land Size by Partner Organization"
          subtitle="Total verified hectares per partner — a sizing signal for loan amounts and collateral expectations."
          loading={orgLand.loading}
          error={orgLand.error}
        >
          <ThemedBarChart
            data={orgLand.data as unknown as Record<string, unknown>[]}
            xKey="organization"
            yKey="total_hectares"
            color="#7c3aed"
          />
        </ChartCard>

        <ChartCard
          title="Production Volume by Crop"
          subtitle="Verified production (kg) aggregated by crop — where physical supply is concentrated."
          loading={cropProduction.loading}
          error={cropProduction.error}
        >
          <ThemedBarChart
            data={cropProduction.data as unknown as Record<string, unknown>[]}
            xKey="crop_type"
            yKey="total_kg"
            color="#f4a261"
          />
        </ChartCard>

        <ChartCard
          title="Loan-Readiness by Product"
          subtitle="How many farmers in the portfolio currently qualify for each catalog product, via the MATCH engine."
          loading={eligibility.loading}
          error={eligibility.error}
        >
          <ThemedBarChart
            data={eligibility.data as unknown as Record<string, unknown>[]}
            xKey="product_id"
            yKey="eligible_count"
          />
          {!eligibility.loading && !eligibility.error && eligibility.data.some((p) => p.eligible_count === 0) ? (
            <p className="mt-3 text-xs text-secondary">
              Most products require attesting institutions to clear a trust-score bar (0.7–0.8)
              that newly-onboarded cooperatives haven&apos;t reached yet — this is the cold-start
              problem, visible directly in the data rather than hidden.
            </p>
          ) : null}
        </ChartCard>
      </div>
    </main>
  );
}
