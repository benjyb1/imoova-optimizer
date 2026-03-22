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
}

export default function ResultsList({ results, onReset }: ResultsListProps) {
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
    () => applyFilters(results, filters),
    [results, filters]
  );

  const completeCount = results.filter(
    (r) => r.total_price_gbp !== null
  ).length;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      {/* Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-text">
            {completeCount} holidays found
          </h2>
          <p className="text-sm text-text-muted">
            {results.length - completeCount > 0 &&
              `(${results.length - completeCount} with incomplete pricing)`}
          </p>
        </div>
        <button
          type="button"
          onClick={onReset}
          className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-text-muted
            transition-colors hover:border-primary hover:text-primary"
        >
          New Search
        </button>
      </div>

      {/* Filters */}
      <Filters results={results} filters={filters} onChange={setFilters} />

      {/* Results grid */}
      {filtered.length > 0 ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((deal, i) => (
            <ResultCard key={i} deal={deal} />
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
