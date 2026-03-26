"use client";

import { useState, useEffect, useCallback } from "react";
import SearchForm from "@/components/SearchForm";
import ProgressView from "@/components/ProgressView";
import ResultsList from "@/components/ResultsList";
import SearchHistory from "@/components/SearchHistory";
import { useSearch } from "@/lib/useSearch";
import { SearchRequest, SavedSearch, EnrichedDeal } from "@/lib/types";
import {
  loadSearchHistory,
  saveSearch,
  deleteSearch,
  saveInProgress,
  loadInProgress,
  clearInProgress,
} from "@/lib/searchHistory";

export default function Home() {
  const { state, progress, results, error, startSearch, reset } = useSearch();

  // Sidebar state
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchHistory, setSearchHistory] = useState<SavedSearch[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);

  // When viewing a past search, these hold the displayed results
  const [viewingPastSearch, setViewingPastSearch] = useState(false);
  const [pastResults, setPastResults] = useState<EnrichedDeal[]>([]);
  const [pastRequest, setPastRequest] = useState<SearchRequest | null>(null);

  // Refresh state — old results stay visible while new ones load
  const [isRefreshing, setIsRefreshing] = useState(false);
  const refreshSearch = useSearch();

  // Current search params (for saving)
  const [currentRequest, setCurrentRequest] = useState<SearchRequest | null>(null);

  // Load history on mount, and restore any interrupted search
  useEffect(() => {
    setSearchHistory(loadSearchHistory());

    const interrupted = loadInProgress();
    if (interrupted && interrupted.results.length > 0) {
      setViewingPastSearch(true);
      setPastResults(interrupted.results);
      setPastRequest(interrupted.request);
      setCurrentRequest(interrupted.request);
      // Save the partial results to history so they're not lost
      const saved = saveSearch(interrupted.request, interrupted.results);
      setSearchHistory(loadSearchHistory());
      setActiveHistoryId(saved.id);
      clearInProgress();
    }
  }, []);

  // Cache in-progress results every 100 deals
  useEffect(() => {
    if (
      state === "searching" &&
      currentRequest &&
      results.length > 0 &&
      results.length % 100 === 0
    ) {
      saveInProgress(currentRequest, results);
    }
  }, [state, results.length, currentRequest]);

  // Save search when it completes, then clear the in-progress cache
  useEffect(() => {
    if (state === "complete" && currentRequest && results.length > 0) {
      const saved = saveSearch(currentRequest, results);
      clearInProgress();
      setSearchHistory(loadSearchHistory());
      setActiveHistoryId(saved.id);
    }
  }, [state, results, currentRequest]);

  // When a refresh completes, swap in the new results
  useEffect(() => {
    if (refreshSearch.state === "complete" && isRefreshing && pastRequest) {
      const newResults = refreshSearch.results;
      setPastResults(newResults);
      const saved = saveSearch(pastRequest, newResults);
      setSearchHistory(loadSearchHistory());
      setActiveHistoryId(saved.id);
      setIsRefreshing(false);
      refreshSearch.reset();
    }
  }, [refreshSearch.state, isRefreshing, pastRequest, refreshSearch.results]);

  const handleSearch = (params: SearchRequest) => {
    setCurrentRequest(params);
    setViewingPastSearch(false);
    setActiveHistoryId(null);
    startSearch(params);
  };

  const handleSelectHistory = useCallback((search: SavedSearch) => {
    // Show saved results immediately
    reset();
    setViewingPastSearch(true);
    setPastResults(search.results);
    setPastRequest(search.request);
    setActiveHistoryId(search.id);
    setCurrentRequest(search.request);
  }, [reset]);

  const handleDeleteHistory = useCallback((id: string) => {
    deleteSearch(id);
    setSearchHistory(loadSearchHistory());
    if (activeHistoryId === id) {
      setViewingPastSearch(false);
      setPastResults([]);
      setPastRequest(null);
      setActiveHistoryId(null);
    }
  }, [activeHistoryId]);

  const handleRefresh = useCallback(() => {
    const request = viewingPastSearch ? pastRequest : currentRequest;
    if (!request || isRefreshing) return;
    setIsRefreshing(true);
    // If viewing a live completed search, switch to "past search" view
    // so old results stay visible
    if (!viewingPastSearch && state === "complete") {
      setViewingPastSearch(true);
      setPastResults(results);
      setPastRequest(request);
    }
    refreshSearch.startSearch(request);
  }, [pastRequest, currentRequest, isRefreshing, refreshSearch.startSearch, viewingPastSearch, state, results]);

  const handleReset = () => {
    reset();
    setViewingPastSearch(false);
    setPastResults([]);
    setPastRequest(null);
    setActiveHistoryId(null);
    setCurrentRequest(null);
  };

  const numPeople = currentRequest?.num_people ?? pastRequest?.num_people ?? 1;

  // What to show in the main area
  const showIdle = state === "idle" && !viewingPastSearch;
  const showSearching = state === "searching" && !viewingPastSearch;
  const showResults = (state === "complete" && !viewingPastSearch) || viewingPastSearch;
  const showError = state === "error" && !viewingPastSearch;

  const displayResults = viewingPastSearch ? pastResults : results;

  return (
    <>
      {/* Sidebar */}
      <SearchHistory
        searches={searchHistory}
        activeId={activeHistoryId}
        onSelect={handleSelectHistory}
        onDelete={handleDeleteHistory}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />

      {/* Main content — shifts right when sidebar is open */}
      <div
        className="transition-all duration-200 ease-in-out"
        style={{ marginLeft: sidebarOpen ? "280px" : "0px" }}
      >
        <div className="mx-auto w-full max-w-6xl">
          {/* Idle state */}
          {showIdle && (
            <div className="flex min-h-[60vh] items-center justify-center">
              <SearchForm onSearch={handleSearch} />
            </div>
          )}

          {/* Searching state */}
          {showSearching && (
            <ProgressView progress={progress} results={results} numPeople={numPeople} />
          )}

          {/* Results state (live or past search) */}
          {showResults && (
            <ResultsList
              results={displayResults}
              onReset={handleReset}
              numPeople={numPeople}
              isRefreshing={isRefreshing}
              refreshProgress={
                isRefreshing
                  ? { searched: refreshSearch.progress.searched, total: refreshSearch.progress.total }
                  : undefined
              }
              onRefresh={handleRefresh}
            />
          )}

          {/* Error state */}
          {showError && (
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
                onClick={handleReset}
                className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white
                  transition-colors hover:bg-primary-dark"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
