"use client";

import SearchForm from "@/components/SearchForm";
import ProgressView from "@/components/ProgressView";
import ResultsList from "@/components/ResultsList";
import { useSearch } from "@/lib/useSearch";
import { SearchRequest } from "@/lib/types";

export default function Home() {
  const { state, progress, results, error, startSearch, reset } = useSearch();

  const handleSearch = (params: SearchRequest) => {
    startSearch(params);
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      {/* Search state */}
      {state === "idle" && (
        <div className="flex min-h-[60vh] items-center justify-center">
          <SearchForm onSearch={handleSearch} />
        </div>
      )}

      {/* Searching state */}
      {state === "searching" && (
        <ProgressView progress={progress} results={results} />
      )}

      {/* Complete state */}
      {state === "complete" && (
        <ResultsList results={results} onReset={reset} />
      )}

      {/* Error state */}
      {state === "error" && (
        <div className="mx-auto max-w-md space-y-4 text-center">
          <div className="rounded-xl border border-red-200 bg-red-50 p-6">
            <p className="text-lg font-semibold text-red-700">
              Something went wrong
            </p>
            <p className="mt-2 text-sm text-red-600">
              {error || "An unexpected error occurred."}
            </p>
          </div>
          <button
            type="button"
            onClick={reset}
            className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white
              transition-colors hover:bg-primary-dark"
          >
            Try Again
          </button>
        </div>
      )}
    </div>
  );
}
