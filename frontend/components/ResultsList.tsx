"use client";

import { useState, useMemo, useEffect } from "react";
import { EnrichedDeal } from "@/lib/types";
import Filters, {
  FilterState,
  getDefaultFilters,
  applyFilters,
} from "./Filters";
import ResultCard from "./ResultCard";

function formatEta(seconds: number): string {
  if (seconds <= 0) return "";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins > 0) return `~${mins}m ${secs}s remaining`;
  return `~${secs}s remaining`;
}

interface ResultsListProps {
  results: EnrichedDeal[];
  onReset: () => void;
  numPeople?: number;
  isRefreshing?: boolean;
  refreshProgress?: { searched: number; total: number };
  onRefresh?: () => void;
  isStreaming?: boolean;
  streamProgress?: { searched: number; total: number; etaSeconds: number };
  hasError?: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
}

export default function ResultsList({
  results,
  onReset,
  numPeople = 1,
  isRefreshing = false,
  refreshProgress,
  onRefresh,
  isStreaming = false,
  streamProgress,
  hasError = false,
  errorMessage,
  onRetry,
}: ResultsListProps) {
  const [filters, setFilters] = useState<FilterState>(getDefaultFilters);

  // Update max price when results first load
  useEffect(() => {
    const max = results.reduce(
      (m, r) => (r.total_price_gbp !== null && r.total_price_gbp > m ? r.total_price_gbp : m),
      0
    );
    const rounded = Math.ceil(max / 50) * 50 || 500;
    setFilters((prev) => ({ ...prev, maxPrice: rounded }));
  }, [results]);

  const filtered = useMemo(
    () => applyFilters(results, filters, numPeople),
    [results, filters, numPeople]
  );

  const completeCount = results.filter(
    (r) => r.total_price_gbp !== null
  ).length;

  const streamPercent =
    streamProgress && streamProgress.total > 0
      ? Math.round((streamProgress.searched / streamProgress.total) * 100)
      : 0;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      {/* Streaming progress bar */}
      {isStreaming && streamProgress && streamProgress.total > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all duration-500 ease-out"
              style={{ width: `${streamPercent}%` }}
            />
          </div>
          <div className="mt-2 flex justify-between text-xs text-text-muted">
            <span>
              {streamProgress.searched} / {streamProgress.total} routes searched
            </span>
            {streamProgress.etaSeconds > 0 && (
              <span>{formatEta(streamProgress.etaSeconds)}</span>
            )}
          </div>
        </div>
      )}

      {/* Streaming but no progress yet (pre-search phase during retry) */}
      {isStreaming && (!streamProgress || streamProgress.total === 0) && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-center gap-2 text-sm text-text-muted">
            <div className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-2 w-2 rounded-full bg-primary animate-pulse"
                  style={{ animationDelay: `${i * 0.2}s` }}
                />
              ))}
            </div>
            <span>Loading flights...</span>
          </div>
        </div>
      )}

      {/* Error banner with retry */}
      {hasError && !isStreaming && (
        <div className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-5 py-3">
          <div>
            <p className="text-sm font-medium text-amber-800">
              Search interrupted
            </p>
            <p className="text-xs text-amber-600">
              {errorMessage || "Something went wrong, but your results so far are shown below."}
            </p>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="ml-4 shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white
                transition-colors hover:bg-primary-dark"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {/* Refresh loading bar */}
      {isRefreshing && (
        <div className="overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-1.5 rounded-full bg-gradient-to-r from-primary to-accent transition-all duration-500 ease-out"
            style={{
              width: refreshProgress && refreshProgress.total > 0
                ? `${Math.round((refreshProgress.searched / refreshProgress.total) * 100)}%`
                : "0%",
            }}
          />
          <p className="mt-1 text-center text-xs text-text-muted">
            Refreshing flights...
            {refreshProgress && refreshProgress.total > 0 &&
              ` (${refreshProgress.searched}/${refreshProgress.total})`}
          </p>
        </div>
      )}

      {/* Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-text">
            {completeCount} holiday{completeCount !== 1 ? "s" : ""} found
            {isStreaming && " so far"}
            {numPeople > 1 && (
              <span className="ml-2 text-base font-normal text-text-muted">
                ({numPeople} travellers)
              </span>
            )}
          </h2>
          <p className="text-sm text-text-muted">
            {results.length - completeCount > 0 &&
              `(${results.length - completeCount} with incomplete pricing)`}
          </p>
        </div>
        <div className="flex gap-2">
          {onRefresh && !isStreaming && !hasError && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-text-muted
                transition-colors hover:border-primary hover:text-primary
                disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRefreshing ? "Refreshing..." : "Refresh Flights"}
            </button>
          )}
          <button
            type="button"
            onClick={onReset}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-text-muted
              transition-colors hover:border-primary hover:text-primary"
          >
            New Search
          </button>
        </div>
      </div>

      {/* Filters */}
      <Filters results={results} filters={filters} onChange={setFilters} />

      {/* Results grid */}
      {filtered.length > 0 ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((deal, i) => (
            <ResultCard key={i} deal={deal} numPeople={numPeople} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center">
          <p className="text-lg text-text-muted">
            {isStreaming ? "Results loading..." : "No results match your filters"}
          </p>
          {!isStreaming && (
            <p className="mt-1 text-sm text-text-muted/60">
              Try adjusting the price range or enabling more countries
            </p>
          )}
        </div>
      )}
    </div>
  );
}
