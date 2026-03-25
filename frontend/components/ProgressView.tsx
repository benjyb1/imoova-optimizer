"use client";

import { SearchProgress, EnrichedDeal } from "@/lib/types";
import ResultCard from "./ResultCard";

interface ProgressViewProps {
  progress: SearchProgress;
  results: EnrichedDeal[];
  numPeople?: number;
}

function formatEta(seconds: number): string {
  if (seconds <= 0) return "";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins > 0) return `~${mins}m ${secs}s remaining`;
  return `~${secs}s remaining`;
}

function getStepLabel(step: string): string {
  switch (step) {
    case "starting":
      return "Starting search...";
    case "scraping":
      return "Scraping Imoova deals...";
    case "filtering":
      return "Filtering deals...";
    case "flights":
      return "Searching flights...";
    default:
      return "Working...";
  }
}

export default function ProgressView({ progress, results, numPeople = 1 }: ProgressViewProps) {
  const progressPercent =
    progress.total > 0
      ? Math.round((progress.searched / progress.total) * 100)
      : 0;

  const isFlightPhase = progress.step === "flights";

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8">
      {/* Progress section */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {/* Campervan animation */}
        <div className="mb-6 flex justify-center">
          <div className="relative h-16 w-full max-w-md overflow-hidden">
            {/* Road */}
            <div className="absolute bottom-2 left-0 right-0 h-1 rounded-full bg-slate-200" />
            {/* Dashes on road */}
            <div className="absolute bottom-2.5 left-0 right-0 flex gap-3">
              {Array.from({ length: 20 }).map((_, i) => (
                <div
                  key={i}
                  className="h-px w-3 bg-slate-300 animate-[slideLeft_2s_linear_infinite]"
                  style={{ animationDelay: `${i * 0.1}s` }}
                />
              ))}
            </div>
            {/* Campervan emoji */}
            <div
              className="absolute bottom-3 text-3xl"
              style={{ left: `${Math.min(progressPercent, 90)}%`, transition: "left 0.5s ease-out" }}
            >
              <span role="img" aria-label="campervan">
                &#x1F690;
              </span>
            </div>
          </div>
        </div>

        {/* Step label */}
        <div className="mb-2 text-center">
          <p className="text-lg font-semibold text-text">
            {progress.message || getStepLabel(progress.step)}
          </p>
        </div>

        {/* Progress bar (only during flights phase) */}
        {isFlightPhase && progress.total > 0 && (
          <div className="mb-2">
            <div className="h-3 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all duration-500 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <div className="mt-1.5 flex justify-between text-xs text-text-muted">
              <span>
                {progress.searched} / {progress.total} routes searched
              </span>
              {progress.etaSeconds > 0 && (
                <span>{formatEta(progress.etaSeconds)}</span>
              )}
            </div>
          </div>
        )}

        {/* Pulsing dots for non-flight phases */}
        {!isFlightPhase && (
          <div className="flex justify-center gap-1.5 py-2">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-2.5 w-2.5 rounded-full bg-primary animate-pulse"
                style={{ animationDelay: `${i * 0.2}s` }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Results streaming in */}
      {results.length > 0 && (
        <div>
          <p className="mb-4 text-center text-sm font-medium text-text-muted">
            {results.length} holiday{results.length !== 1 ? "s" : ""} found so
            far...
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {results
              .filter((r) => r.total_price_gbp !== null)
              .sort((a, b) => (a.total_price_gbp ?? 999) - (b.total_price_gbp ?? 999))
              .slice(0, 6)
              .map((deal, i) => (
                <ResultCard key={i} deal={deal} numPeople={numPeople} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
