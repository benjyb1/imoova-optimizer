"use client";

import { useState, useMemo, useEffect } from "react";
import { EnrichedDeal } from "@/lib/types";
import Filters, {
  FilterState,
  getDefaultFilters,
  applyFilters,
} from "./Filters";
import ResultCard from "./ResultCard";

interface ResultsListProps {
  results: EnrichedDeal[];
  onReset: () => void;
  numPeople?: number;
  isRefreshing?: boolean;
  refreshProgress?: { searched: number; total: number };
  onRefresh?: () => void;
}

export default function ResultsList({
  results,
  onReset,
  numPeople = 1,
  isRefreshing = false,
  refreshProgress,
  onRefresh,
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

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
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
            {completeCount} holidays found
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
          {onRefresh && (
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
            No results match your filters
          </p>
          <p className="mt-1 text-sm text-text-muted/60">
            Try adjusting the price range or enabling more countries
          </p>
        </div>
      )}
    </div>
  );
}
