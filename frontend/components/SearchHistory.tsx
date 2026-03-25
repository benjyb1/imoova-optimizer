"use client";

import { SavedSearch } from "@/lib/types";

interface SearchHistoryProps {
  searches: SavedSearch[];
  activeId: string | null;
  onSelect: (search: SavedSearch) => void;
  onDelete: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

function timeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  return `${days}d ago`;
}

function formatDateRange(earliest?: string, latest?: string): string {
  if (!earliest || !latest) return "";
  const fmt = (s: string) => {
    const d = new Date(s + "T00:00:00");
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  };
  return `${fmt(earliest)} – ${fmt(latest)}`;
}

export default function SearchHistory({
  searches,
  activeId,
  onSelect,
  onDelete,
  isOpen,
  onToggle,
}: SearchHistoryProps) {
  return (
    <>
      {/* Toggle button (always visible) */}
      <button
        type="button"
        onClick={onToggle}
        className="fixed left-0 top-1/2 z-30 -translate-y-1/2 rounded-r-lg bg-white
          border border-l-0 border-slate-200 px-1.5 py-4 shadow-md
          transition-all hover:bg-slate-50"
        style={{ left: isOpen ? "280px" : "0px", transition: "left 0.2s ease" }}
      >
        <svg
          className={`h-5 w-5 text-text-muted transition-transform ${isOpen ? "rotate-180" : ""}`}
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
      </button>

      {/* Sidebar panel */}
      <div
        className="fixed left-0 top-0 z-20 h-full w-[280px] border-r border-slate-200 bg-white
          shadow-lg transition-transform duration-200 ease-in-out overflow-y-auto"
        style={{ transform: isOpen ? "translateX(0)" : "translateX(-100%)" }}
      >
        <div className="p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
            Past Searches
          </h3>
        </div>

        {searches.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-text-muted/60">
            No saved searches yet
          </div>
        ) : (
          <div className="space-y-1 px-2 pb-4">
            {searches.map((search) => (
              <div
                key={search.id}
                className={`group relative rounded-lg p-3 cursor-pointer transition-colors ${
                  activeId === search.id
                    ? "bg-primary/10 border border-primary/30"
                    : "hover:bg-slate-50 border border-transparent"
                }`}
                onClick={() => onSelect(search)}
              >
                {/* Delete button */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(search.id);
                  }}
                  className="absolute right-2 top-2 opacity-0 group-hover:opacity-100
                    rounded p-0.5 text-text-muted/40 hover:text-red-500 transition-all"
                >
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>

                <div className="text-sm font-medium text-text">
                  {search.request.home_city}
                </div>
                <div className="mt-0.5 text-xs text-text-muted">
                  {search.request.min_days}–{search.request.max_days} days
                  {search.request.num_people && search.request.num_people > 1 && (
                    <span> · {search.request.num_people} people</span>
                  )}
                </div>
                <div className="mt-0.5 text-xs text-text-muted">
                  {formatDateRange(
                    search.request.earliest_departure,
                    search.request.latest_return
                  )}
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-xs font-medium text-primary">
                    {search.completeCount} results
                  </span>
                  <span className="text-xs text-text-muted/60">
                    {timeAgo(search.savedAt)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
