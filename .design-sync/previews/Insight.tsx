import * as React from 'react';
import { Insight } from 'verifarms-frontend';

export const CopilotAnswer = () => (
  <Insight
    title="Copilot answer"
    text="Farmer F-1 reports 2.4 ha of maize. The Sentinel-2 NDVI cross-check confirms ~2.3 ha of vegetated area (within 4%), and the cooperative's attestation corroborates the land size. This claim is well-supported for an input loan."
  />
);

export const WithoutTitle = () => (
  <Insight text="No conflicting attestations were found across the three sources reviewed for this farmer." />
);

export const EligibilitySummary = () => (
  <Insight
    title="Eligibility summary"
    text="Eligible for the Smallholder Crop Loan. Trust score 0.78 clears the 0.70 threshold; verified land size and harvest history both satisfy the lender's rules."
  />
);
