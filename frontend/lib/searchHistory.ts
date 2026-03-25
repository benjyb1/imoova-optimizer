import { SavedSearch, SearchRequest, EnrichedDeal } from "./types";

const STORAGE_KEY = "imoova-searches";
const MAX_SAVED = 20;

export function loadSearchHistory(): SavedSearch[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as SavedSearch[];
  } catch {
    return [];
  }
}

export function saveSearch(
  request: SearchRequest,
  results: EnrichedDeal[]
): SavedSearch {
  const history = loadSearchHistory();

  // Check for existing search with same params (overwrite it)
  const existingIdx = history.findIndex(
    (s) => searchParamsMatch(s.request, request)
  );

  const completeCount = results.filter(
    (r) => r.total_price_gbp !== null
  ).length;

  const entry: SavedSearch = {
    id: existingIdx >= 0 ? history[existingIdx].id : generateId(),
    request,
    results,
    savedAt: Date.now(),
    completeCount,
    totalCount: results.length,
  };

  if (existingIdx >= 0) {
    history[existingIdx] = entry;
  } else {
    history.unshift(entry);
  }

  // Cap at MAX_SAVED
  const trimmed = history.slice(0, MAX_SAVED);

  localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  return entry;
}

export function deleteSearch(id: string): void {
  const history = loadSearchHistory();
  const filtered = history.filter((s) => s.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

function searchParamsMatch(a: SearchRequest, b: SearchRequest): boolean {
  return (
    a.home_city === b.home_city &&
    a.min_days === b.min_days &&
    a.max_days === b.max_days &&
    a.earliest_departure === b.earliest_departure &&
    a.latest_return === b.latest_return &&
    (a.min_seats ?? null) === (b.min_seats ?? null)
  );
}
