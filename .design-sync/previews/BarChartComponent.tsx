import * as React from 'react';
import { BarChartComponent } from 'verifarms-frontend';

export const CooperativeMetrics = () => (
  <BarChartComponent
    xKey="metric"
    yKey="value"
    data={[
      { metric: 'Members', value: 128 },
      { metric: 'Verified ha', value: 342 },
      { metric: 'Avg trust', value: 74 },
      { metric: 'Active loans', value: 56 },
    ]}
  />
);

export const ClaimsBySource = () => (
  <BarChartComponent
    xKey="source"
    yKey="claims"
    data={[
      { source: 'Coop', claims: 64 },
      { source: 'MFI', claims: 41 },
      { source: 'Satellite', claims: 88 },
      { source: 'Survey', claims: 23 },
    ]}
  />
);
