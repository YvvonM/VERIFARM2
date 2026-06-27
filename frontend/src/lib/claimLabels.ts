// Plain-language labels for reified claim_type values, shared across the
// Partner Portal pages (written for non-technical users -- no raw schema
// field names like "land_size_hectares" shown in the UI).
const CLAIM_TYPE_LABELS: Record<string, string> = {
  land_size_hectares: "Land Size",
  production_volume_kg: "How Much They Produce",
  production_volume: "How Much They Produce",
  credit_history: "Credit History",
  identity: "Identity",
  identity_verified: "Identity",
};

export function friendlyClaimType(claimType: string): string {
  return (
    CLAIM_TYPE_LABELS[claimType] ??
    claimType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}
