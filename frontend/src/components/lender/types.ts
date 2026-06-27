// Shared types for the lender dashboard -- mirror the backend response models
// exactly (app/api/lender.py::EligibleFarmer/EligibleFarmersPage,
// app/models/profiles.py::ClaimDetail/FarmerProfileResponse). No fields are
// invented here; anything not returned by the API is left optional/undefined
// and rendered as "--" rather than fabricated.

export interface VerificationSourceSummary {
  claim_type: string;
  value: string | null;
  source: string | null;
  source_trust: number;
}

export interface MatchedProduct {
  product_id: string;
  lender_name: string;
  eligible: boolean;
}

export interface EligibleFarmer {
  farmer_id: string;
  cooperative_name: string | null;
  crop_types: string[];
  verified_land_hectares: number | null;
  verification_sources: VerificationSourceSummary[];
  matched_products: MatchedProduct[];
}

export interface ClaimDetail {
  value_numeric: number | null;
  confidence: number;
  source_name: string;
  is_authoritative: boolean;
  reputation_score: number | null;
}

export interface FarmerProfileResponse {
  farmer_id: string;
  // phone_number intentionally not declared -- never read or rendered here,
  // so farmer_id and phone never appear together in this UI.
  verified_history: Record<string, ClaimDetail[]>;
}

export function topTrustScore(f: EligibleFarmer): number {
  return f.verification_sources.length > 0
    ? Math.max(...f.verification_sources.map((s) => s.source_trust))
    : 0;
}

export function trustColor(score: number): { badge: string; text: string; ring: string } {
  if (score > 0.7) return { badge: "bg-primary/15 text-primary", text: "text-primary", ring: "#4ade80" };
  if (score >= 0.5) return { badge: "bg-secondary/20 text-secondary", text: "text-secondary", ring: "#f4a261" };
  return { badge: "bg-destructive/15 text-destructive", text: "text-destructive", ring: "#f87171" };
}
