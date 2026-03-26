// ── City / Airport types ─────────────────────────────────────

export interface City {
  name: string;
  country: string;
  airports: string[];
}

// ── Search request ───────────────────────────────────────────

export interface SearchRequest {
  home_city: string;
  min_days?: number;
  max_days?: number;
  min_seats?: number | null;
  earliest_departure?: string; // YYYY-MM-DD
  latest_return?: string; // YYYY-MM-DD
  num_people?: number; // number of travellers (affects per-person cost)
}

// ── Saved search (localStorage) ─────────────────────────────

export interface SavedSearch {
  id: string;
  request: SearchRequest;
  results: EnrichedDeal[];
  savedAt: number; // unix timestamp ms
  completeCount: number;
  totalCount: number;
}

// ── Flight result ────────────────────────────────────────────

export interface FlightResult {
  airline: string;
  departure_airport: string;
  arrival_airport: string;
  departure_time: string;
  price_gbp: number;
  is_direct: boolean;
}

// ── Deal info (from Imoova) ──────────────────────────────────

export interface DealInfo {
  pickup_city: string;
  pickup_country: string;
  dropoff_city: string;
  dropoff_country: string;
  pickup_date: string; // YYYY-MM-DD
  dropoff_date: string; // YYYY-MM-DD
  drive_days: number;
  vehicle_type: string;
  seats: number;
  imoova_price_gbp: number;
  imoova_url: string;
}

// ── Enriched deal (deal + flights + total) ───────────────────

export interface EnrichedDeal {
  deal: DealInfo;
  drive_hours: number | null; // estimated driving hours between cities
  outbound_flight: FlightResult | null;
  return_flight: FlightResult | null;
  outbound_is_home: boolean; // user lives in pickup city
  return_is_home: boolean; // user lives in dropoff city
  total_price_gbp: number | null; // null if flights incomplete
  google_flights_outbound_url: string | null;
  google_flights_return_url: string | null;
}

// ── WebSocket message types ──────────────────────────────────

export interface WSStatusMessage {
  type: "status";
  step: "scraping" | "filtering" | "flights";
  message: string;
}

export interface WSProgressMessage {
  type: "progress";
  step: "flights";
  searched: number;
  total: number;
  eta_seconds: number;
}

export interface WSResultMessage {
  type: "result";
  deal: EnrichedDeal;
}

export interface WSCompleteMessage {
  type: "complete";
  total_results: number;
  complete_results: number;
}

export interface WSErrorMessage {
  type: "error";
  message: string;
}

export interface WSPingMessage {
  type: "ping";
}

export type WSMessage =
  | WSStatusMessage
  | WSProgressMessage
  | WSResultMessage
  | WSCompleteMessage
  | WSErrorMessage
  | WSPingMessage;

// ── Search state machine ─────────────────────────────────────

export type SearchState = "idle" | "searching" | "complete" | "error";

export interface SearchProgress {
  step: string;
  message: string;
  searched: number;
  total: number;
  etaSeconds: number;
}
