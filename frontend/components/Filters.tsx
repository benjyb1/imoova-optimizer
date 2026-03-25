"use client";

import { useMemo } from "react";
import { EnrichedDeal } from "@/lib/types";
import { getFlagEmoji } from "@/lib/countries";

export type SortOption = "price" | "departure" | "duration";

export interface FilterState {
  sort: SortOption;
  excludedCountries: Set<string>;
  maxPrice: number;
  showIncomplete: boolean;
}

interface FiltersProps {
  results: EnrichedDeal[];
  filters: FilterState;
  onChange: (filters: FilterState) => void;
}

export function getDefaultFilters(): FilterState {
  return {
    sort: "price",
    excludedCountries: new Set(),
    maxPrice: 500,
    showIncomplete: false,
  };
}

function perPersonPrice(r: EnrichedDeal, numPeople: number): number | null {
  if (r.total_price_gbp === null) return null;
  return (
    (r.total_price_gbp - r.deal.imoova_price_gbp) +
    r.deal.imoova_price_gbp / numPeople
  );
}

export function applyFilters(
  results: EnrichedDeal[],
  filters: FilterState,
  numPeople: number = 1
): EnrichedDeal[] {
  let filtered = results.filter((r) => {
    // Incomplete filter
    if (!filters.showIncomplete && r.total_price_gbp === null) return false;

    // Max price filter (using per-person price)
    const pp = perPersonPrice(r, numPeople);
    if (pp !== null && pp > filters.maxPrice)
      return false;

    // Country filter — check both pickup and dropoff countries
    const countries = new Set([
      r.deal.pickup_country,
      r.deal.dropoff_country,
    ]);
    for (const c of countries) {
      if (filters.excludedCountries.has(c)) return false;
    }

    return true;
  });

  // Sort
  filtered.sort((a, b) => {
    switch (filters.sort) {
      case "price":
        return (perPersonPrice(a, numPeople) ?? 9999) - (perPersonPrice(b, numPeople) ?? 9999);
      case "departure":
        return a.deal.pickup_date.localeCompare(b.deal.pickup_date);
      case "duration":
        return a.deal.drive_days - b.deal.drive_days;
      default:
        return 0;
    }
  });

  return filtered;
}

export default function Filters({ results, filters, onChange }: FiltersProps) {
  // Extract unique countries from results
  const countries = useMemo(() => {
    const set = new Set<string>();
    for (const r of results) {
      set.add(r.deal.pickup_country);
      set.add(r.deal.dropoff_country);
    }
    return Array.from(set).sort();
  }, [results]);

  // Calculate max price from results for slider range
  const maxPriceInResults = useMemo(() => {
    let max = 0;
    for (const r of results) {
      if (r.total_price_gbp !== null && r.total_price_gbp > max) {
        max = r.total_price_gbp;
      }
    }
    return Math.ceil(max / 50) * 50 || 500;
  }, [results]);

  const toggleCountry = (country: string) => {
    const next = new Set(filters.excludedCountries);
    if (next.has(country)) {
      next.delete(country);
    } else {
      next.add(country);
    }
    onChange({ ...filters, excludedCountries: next });
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
      {/* Sort */}
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-text-muted uppercase tracking-wide">
          Sort
        </label>
        <select
          value={filters.sort}
          onChange={(e) =>
            onChange({ ...filters, sort: e.target.value as SortOption })
          }
          className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm focus:border-primary
            focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          <option value="price">Price</option>
          <option value="departure">Departure Date</option>
          <option value="duration">Trip Duration</option>
        </select>
      </div>

      {/* Divider */}
      <div className="hidden sm:block h-6 w-px bg-slate-200" />

      {/* Country chips */}
      <div className="flex flex-wrap gap-1.5">
        {countries.map((country) => {
          const isExcluded = filters.excludedCountries.has(country);
          return (
            <button
              key={country}
              type="button"
              onClick={() => toggleCountry(country)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
                isExcluded
                  ? "bg-slate-100 text-text-muted/50 line-through"
                  : "bg-primary/10 text-primary hover:bg-primary/20"
              }`}
            >
              {getFlagEmoji(country)} {country}
              {!isExcluded && (
                <span className="ml-1 text-primary/40">&times;</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Divider */}
      <div className="hidden sm:block h-6 w-px bg-slate-200" />

      {/* Max price */}
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-text-muted uppercase tracking-wide">
          Max
        </label>
        <input
          type="range"
          min={0}
          max={maxPriceInResults}
          step={10}
          value={filters.maxPrice > maxPriceInResults ? maxPriceInResults : filters.maxPrice}
          onChange={(e) =>
            onChange({ ...filters, maxPrice: Number(e.target.value) })
          }
          className="w-20 accent-primary"
        />
        <span className="text-sm font-medium text-text">
          &pound;{filters.maxPrice > maxPriceInResults ? maxPriceInResults : filters.maxPrice}
        </span>
      </div>

      {/* Divider */}
      <div className="hidden sm:block h-6 w-px bg-slate-200" />

      {/* Show incomplete toggle */}
      <label className="flex cursor-pointer items-center gap-2 text-xs text-text-muted">
        <input
          type="checkbox"
          checked={filters.showIncomplete}
          onChange={(e) =>
            onChange({ ...filters, showIncomplete: e.target.checked })
          }
          className="rounded accent-primary"
        />
        Show incomplete
      </label>
    </div>
  );
}
