"use client";

// Top nav for the lender dashboard (home page). Distinct from PortalNav (used
// by /cooperative/onboard and /partner) so this page's specific requirements
// -- logo, active-link highlight, live verified-farmer counter -- don't
// change the nav on those already-working pages.
import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;
const FALLBACK_VERIFIED_COUNT = 200;

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return headers;
}

export function LenderNav() {
  const [verifiedCount, setVerifiedCount] = useState(FALLBACK_VERIFIED_COUNT);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/v1/macro/cooperative/ORG-TEGEMEO-001/stats`, {
      headers: authHeaders(),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: { total_members?: number }) => {
        if (!cancelled && typeof data.total_members === "number") {
          setVerifiedCount(data.total_members);
        }
      })
      .catch(() => {
        // Keep the hardcoded fallback -- the nav must never show a blank count.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <nav className="flex items-center justify-between border-b border-white/10 bg-white/5 px-6 py-3 backdrop-blur">
      <div className="flex items-center gap-6">
        <Link href="/" className="font-display text-lg uppercase tracking-wide text-primary">
          VeriFarm
        </Link>
        <Link
          href="/"
          className="rounded-full bg-primary/15 px-3 py-1 text-sm font-medium text-primary"
        >
          Farmer Search
        </Link>
        <Link
          href="/cooperative/onboard"
          className="text-sm font-medium text-white/60 hover:text-primary"
        >
          Cooperative Onboard
        </Link>
        <Link href="/partner" className="text-sm font-medium text-white/60 hover:text-primary">
          Partner Portal
        </Link>
        <Link href="/analytics" className="text-sm font-medium text-white/60 hover:text-primary">
          Analytics
        </Link>
      </div>
      <span className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
        Verified Farmers: {verifiedCount}
      </span>
    </nav>
  );
}

export default LenderNav;
