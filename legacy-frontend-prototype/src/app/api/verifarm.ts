const API_BASE = "https://scaling-guide-r5x9p5p49jqh54w-8000.app.github.dev";

export async function fetchAllFarmers() {
  const res = await fetch(`${API_BASE}/api/farmers`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchFarmer(farmerId: string) {
  const res = await fetch(`${API_BASE}/api/farmers/${farmerId}`);
  if (!res.ok) throw new Error(`Not found: ${res.status}`);
  return res.json();
}

export async function searchFarmer(name: string) {
  const res = await fetch(`/api/farmers/search?name=${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

export function openVerificationStream(query: string) {
  return new EventSource(`/api/chat?query=${encodeURIComponent(`verify farmer: ${query}`)}`);
}