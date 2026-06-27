"use client";

// Lender Dashboard -- the primary view. Two panels: farmer search/filter on
// the left, the selected farmer's verified profile on the right. No chat by
// default (the old copilot SSE chat lived here before; this page replaces it
// per the lender-dashboard requirement).
import { useState } from "react";

import { LenderNav } from "@/components/nav/LenderNav";
import { FarmerSearchPanel } from "@/components/lender/FarmerSearchPanel";
import { FarmerProfilePanel } from "@/components/lender/FarmerProfilePanel";
import { EligibleFarmer } from "@/components/lender/types";

export default function Page() {
  const [selected, setSelected] = useState<EligibleFarmer | null>(null);
  const [selectedRegion, setSelectedRegion] = useState("");

  return (
    <div className="flex h-screen flex-col bg-background">
      <LenderNav />
      <div className="flex flex-1 overflow-hidden">
        <div className="w-1/3 min-w-[320px]">
          <FarmerSearchPanel
            selectedFarmerId={selected?.farmer_id ?? null}
            onSelect={(farmer, region) => {
              setSelected(farmer);
              setSelectedRegion(region);
            }}
          />
        </div>
        <div className="w-2/3 flex-1">
          {selected ? (
            <FarmerProfilePanel listFarmer={selected} region={selectedRegion} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-white/40">
              Select a farmer from the list to view their verified profile.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
