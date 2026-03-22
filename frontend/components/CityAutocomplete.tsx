"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { City } from "@/lib/types";
import { fetchCities } from "@/lib/api";

interface CityAutocompleteProps {
  value: City | null;
  onChange: (city: City | null) => void;
  placeholder?: string;
}

export default function CityAutocomplete({
  value,
  onChange,
  placeholder = "Where do you live?",
}: CityAutocompleteProps) {
  const [cities, setCities] = useState<City[]>([]);
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const [loading, setLoading] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // Fetch cities on mount
  useEffect(() => {
    let cancelled = false;
    fetchCities()
      .then((data) => {
        if (!cancelled) {
          setCities(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = query.trim()
    ? cities.filter((c) => {
        const q = query.toLowerCase();
        return (
          c.name.toLowerCase().includes(q) ||
          c.country.toLowerCase().includes(q) ||
          c.airports.some((a) => a.toLowerCase().includes(q))
        );
      })
    : [];

  const handleSelect = useCallback(
    (city: City) => {
      onChange(city);
      setQuery("");
      setIsOpen(false);
      setHighlightIndex(-1);
    },
    [onChange]
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || filtered.length === 0) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightIndex((i) =>
          i < filtered.length - 1 ? i + 1 : 0
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightIndex((i) =>
          i > 0 ? i - 1 : filtered.length - 1
        );
        break;
      case "Enter":
        e.preventDefault();
        if (highlightIndex >= 0 && highlightIndex < filtered.length) {
          handleSelect(filtered[highlightIndex]);
        }
        break;
      case "Escape":
        setIsOpen(false);
        setHighlightIndex(-1);
        break;
    }
  };

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightIndex >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll("li");
      items[highlightIndex]?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightIndex]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        inputRef.current &&
        !inputRef.current.parentElement?.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // If we have a selected value, show the chip
  if (value) {
    return (
      <div className="relative">
        <div className="flex items-center gap-2 rounded-xl border-2 border-primary/30 bg-white px-4 py-3.5 text-lg">
          <span className="flex items-center gap-2 rounded-lg bg-primary/10 px-3 py-1.5 text-primary font-medium">
            {value.name}, {value.country}{" "}
            <span className="text-text-muted text-sm">
              ({value.airports.join(", ")})
            </span>
            <button
              type="button"
              onClick={() => {
                onChange(null);
                setTimeout(() => inputRef.current?.focus(), 0);
              }}
              className="ml-1 text-primary/60 hover:text-primary transition-colors"
              aria-label="Clear selection"
            >
              &times;
            </button>
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setIsOpen(true);
          setHighlightIndex(-1);
        }}
        onFocus={() => {
          if (query.trim()) setIsOpen(true);
        }}
        onKeyDown={handleKeyDown}
        placeholder={loading ? "Loading cities..." : placeholder}
        disabled={loading}
        className="w-full rounded-xl border-2 border-slate-200 bg-white px-5 py-4 text-lg
          placeholder:text-text-muted/60 focus:border-primary focus:outline-none
          focus:ring-2 focus:ring-primary/20 transition-all disabled:opacity-50"
        autoComplete="off"
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      />

      {/* Search icon */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 text-text-muted/40">
        <svg
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
      </div>

      {/* Dropdown */}
      {isOpen && filtered.length > 0 && (
        <ul
          ref={listRef}
          role="listbox"
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-xl border border-slate-200
            bg-white shadow-lg"
        >
          {filtered.slice(0, 20).map((city, i) => (
            <li
              key={`${city.name}-${city.country}`}
              role="option"
              aria-selected={i === highlightIndex}
              className={`cursor-pointer px-5 py-3 transition-colors ${
                i === highlightIndex
                  ? "bg-primary/10 text-primary"
                  : "hover:bg-slate-50"
              }`}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(city);
              }}
              onMouseEnter={() => setHighlightIndex(i)}
            >
              <span className="font-medium">{city.name}</span>
              <span className="text-text-muted">, {city.country}</span>
              <span className="ml-2 text-sm text-text-muted/70">
                ({city.airports.join(", ")})
              </span>
            </li>
          ))}
        </ul>
      )}

      {isOpen && query.trim() && filtered.length === 0 && !loading && (
        <div className="absolute z-50 mt-1 w-full rounded-xl border border-slate-200 bg-white px-5 py-4 text-text-muted shadow-lg">
          No cities found matching &ldquo;{query}&rdquo;
        </div>
      )}
    </div>
  );
}
