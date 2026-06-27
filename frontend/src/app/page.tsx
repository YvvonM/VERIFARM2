"use client";

// Lender Dashboard -- the primary view. Shows the list of already-accredited
// (verified, eligible) farmers; clicking one navigates to its own page
// (/farmer/[farmerId]) for the full detail view, rather than an inline side
// panel -- a real, bookmarkable/shareable page per farmer.
import { useRouter } from "next/navigation";

import { LenderNav } from "@/components/nav/LenderNav";
import { FarmerSearchPanel } from "@/components/lender/FarmerSearchPanel";
import { EligibleFarmer } from "@/components/lender/types";
import { SELECTED_FARMER_STORAGE_KEY } from "@/components/lender/selectedFarmerStorage";

export default function Page() {
  const router = useRouter();

  const handleSelect = (farmer: EligibleFarmer, region: string) => {
    // Hand the already-fetched row + region to the detail page via
    // sessionStorage so it doesn't have to re-fetch the whole list -- the
    // detail page still falls back to fetching it if this is missing (e.g.
    // a bookmarked/shared link opened fresh).
    try {
      sessionStorage.setItem(SELECTED_FARMER_STORAGE_KEY, JSON.stringify({ farmer, region }));
    } catch {
      // sessionStorage can fail (privacy mode, quota) -- the detail page's
      // fetch fallback covers this, so just proceed to navigate regardless.
    }
    router.push(`/farmer/${encodeURIComponent(farmer.farmer_id)}`);
  };

  return (
    <div className="flex h-screen flex-col bg-background">
      <LenderNav />
      <div className="mx-auto w-full max-w-3xl flex-1 overflow-hidden">
        <FarmerSearchPanel selectedFarmerId={null} onSelect={handleSelect} />
      </div>
    </div>
  );
}
