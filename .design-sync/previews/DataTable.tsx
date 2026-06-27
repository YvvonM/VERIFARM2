import * as React from 'react';
import { DataTable } from 'verifarms-frontend';

export const VerifiedHistory = () => (
  <DataTable
    columns={['claim_type', 'value', 'confidence', 'source', 'authoritative']}
    rows={[
      ['land_size_hectares', 2.4, 0.92, 'Meru Farmers Coop', true],
      ['maize_yield_tonnes', 6.1, 0.81, 'AgriCredit MFI', false],
      ['irrigation_method', 'drip', 0.74, 'Field survey', false],
    ]}
    caption="Verified history for farmer F-1."
  />
);

export const EligibilityBreakdown = () => (
  <DataTable
    columns={['claim_type', 'satisfied', 'required_min', 'required_max', 'matched_value']}
    rows={[
      ['land_size_hectares', true, 1.0, null, 2.4],
      ['trust_score', true, 0.7, null, 0.78],
      ['credit_history', false, 1, null, 0],
    ]}
    caption="Eligibility: NOT eligible."
  />
);

export const Empty = () => (
  <DataTable columns={['result']} rows={[]} caption="No matching data was found." />
);
