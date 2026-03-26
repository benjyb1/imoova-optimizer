"use client";

import { useState, FormEvent } from "react";
import CityAutocomplete from "./CityAutocomplete";
import { City, SearchRequest } from "@/lib/types";

interface SearchFormProps {
  onSearch: (params: SearchRequest) => void;
}

function formatDate(d: Date): string {
  return d.toISOString().split("T")[0];
}

function defaultEarliestDeparture(): string {
  const fallback = new Date();
  fallback.setDate(fallback.getDate() + 3);
  const target = new Date("2026-04-03");
  return formatDate(target < fallback ? fallback : target);
}

function defaultLatestReturn(): string {
  const fallback = new Date();
  fallback.setDate(fallback.getDate() + 28);
  const target = new Date("2026-04-14");
  return formatDate(target < fallback ? fallback : target);
}

export default function SearchForm({ onSearch }: SearchFormProps) {
  const [city, setCity] = useState<City | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  const [minDays, setMinDays] = useState(5);
  const [maxDays, setMaxDays] = useState(10);
  const [minSeats, setMinSeats] = useState<number | null>(null);
  const [numPeople, setNumPeople] = useState(1);
  const [earliestDeparture, setEarliestDeparture] = useState(
    defaultEarliestDeparture
  );
  const [latestReturn, setLatestReturn] = useState(defaultLatestReturn);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!city) return;

    onSearch({
      home_city: city.name,
      min_days: minDays,
      max_days: maxDays,
      min_seats: minSeats,
      num_people: numPeople,
      earliest_departure: earliestDeparture,
      latest_return: latestReturn,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-xl space-y-6">
      {/* Hero section */}
      <div className="text-center">
        <h1 className="text-4xl font-bold text-text">
          Find Your Next{" "}
          <span className="text-accent">Campervan Adventure</span>
        </h1>
        <p className="mt-3 text-text-muted text-lg">
          Free Imoova relocations + cheap flights = amazing road trips
        </p>
      </div>

      {/* City input */}
      <div>
        <CityAutocomplete
          value={city}
          onChange={setCity}
          placeholder="Where do you live?"
        />
      </div>

      {/* More options toggle */}
      <button
        type="button"
        onClick={() => setShowOptions(!showOptions)}
        className="flex items-center gap-1.5 text-sm text-text-muted hover:text-primary transition-colors"
      >
        <svg
          className={`h-4 w-4 transition-transform ${showOptions ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
        More options
      </button>

      {/* Collapsible options */}
      {showOptions && (
        <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-5">
          {/* Trip duration range */}
          <div>
            <label className="mb-2 block text-sm font-medium text-text">
              Trip duration: {minDays} – {maxDays} days
            </label>
            <div className="flex items-center gap-4">
              <span className="text-xs text-text-muted">Min</span>
              <input
                type="range"
                min={1}
                max={25}
                value={minDays}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setMinDays(v);
                  if (v > maxDays) setMaxDays(v);
                }}
                className="flex-1 accent-primary"
              />
              <span className="w-6 text-center text-sm font-medium">{minDays}</span>
            </div>
            <div className="mt-2 flex items-center gap-4">
              <span className="text-xs text-text-muted">Max</span>
              <input
                type="range"
                min={1}
                max={25}
                value={maxDays}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setMaxDays(v);
                  if (v < minDays) setMinDays(v);
                }}
                className="flex-1 accent-primary"
              />
              <span className="w-6 text-center text-sm font-medium">{maxDays}</span>
            </div>
          </div>

          {/* Min seats */}
          <div>
            <label className="mb-2 block text-sm font-medium text-text">
              Minimum seats
            </label>
            <select
              value={minSeats ?? ""}
              onChange={(e) =>
                setMinSeats(e.target.value ? Number(e.target.value) : null)
              }
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-primary
                focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <option value="">Any</option>
              <option value="2">2+</option>
              <option value="3">3+</option>
              <option value="4">4+</option>
              <option value="5">5+</option>
            </select>
          </div>

          {/* Number of people */}
          <div>
            <label className="mb-2 block text-sm font-medium text-text">
              Number of travellers
            </label>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setNumPeople(Math.max(1, numPeople - 1))}
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-lg
                  font-medium text-text-muted transition-colors hover:border-primary hover:text-primary"
              >
                &minus;
              </button>
              <span className="w-8 text-center text-lg font-semibold text-text">
                {numPeople}
              </span>
              <button
                type="button"
                onClick={() => setNumPeople(Math.min(10, numPeople + 1))}
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-lg
                  font-medium text-text-muted transition-colors hover:border-primary hover:text-primary"
              >
                +
              </button>
              <span className="text-xs text-text-muted">
                Van hire cost split between travellers
              </span>
            </div>
          </div>

          {/* Date pickers */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-text">
                Earliest departure
              </label>
              <input
                type="date"
                value={earliestDeparture}
                onChange={(e) => setEarliestDeparture(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm
                  focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-text">
                Latest return
              </label>
              <input
                type="date"
                value={latestReturn}
                onChange={(e) => setLatestReturn(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm
                  focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
          </div>
        </div>
      )}

      {/* Submit button */}
      <button
        type="submit"
        disabled={!city}
        className="w-full rounded-xl bg-accent px-8 py-4 text-lg font-bold text-white shadow-lg
          shadow-accent/30 transition-all hover:bg-accent/90 hover:shadow-xl
          hover:shadow-accent/40 disabled:cursor-not-allowed disabled:opacity-40
          disabled:shadow-none active:scale-[0.98]"
      >
        Find Holidays
      </button>
    </form>
  );
}
