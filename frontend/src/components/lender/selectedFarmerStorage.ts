// Shared sessionStorage key for handing the already-fetched search-result row
// from the dashboard list (app/page.tsx) to the per-farmer detail page
// (app/farmer/[farmerId]/page.tsx), so the detail page doesn't have to
// re-fetch the whole list when navigated to normally. The detail page still
// falls back to fetching if this is absent or stale (bookmarked/shared link).
export const SELECTED_FARMER_STORAGE_KEY = "verifarm:selectedFarmer";
