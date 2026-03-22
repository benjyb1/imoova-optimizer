import { City, SearchRequest } from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchCities(): Promise<City[]> {
  const res = await fetch(`${BASE_URL}/api/cities`);
  if (!res.ok) throw new Error("Failed to fetch cities");
  return res.json();
}

export async function createSearch(
  params: SearchRequest
): Promise<{ job_id: string }> {
  const res = await fetch(`${BASE_URL}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Search failed: ${body}`);
  }
  return res.json();
}

export async function fetchResults(
  jobId: string
): Promise<{ results: import("./types").EnrichedDeal[] }> {
  const res = await fetch(`${BASE_URL}/api/results/${jobId}`);
  if (!res.ok) throw new Error("Failed to fetch results");
  return res.json();
}

export function getWebSocketUrl(jobId: string): string {
  const wsBase = BASE_URL.replace(/^http/, "ws");
  return `${wsBase}/ws/job/${jobId}`;
}
