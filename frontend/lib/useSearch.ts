"use client";

import { useState, useCallback, useRef } from "react";
import {
  SearchState,
  SearchProgress,
  EnrichedDeal,
  WSMessage,
  SearchRequest,
} from "./types";
import { createSearch, getWebSocketUrl } from "./api";

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY_MS = 2000;

export function useSearch() {
  const [state, setState] = useState<SearchState>("idle");
  const [progress, setProgress] = useState<SearchProgress>({
    step: "",
    message: "",
    searched: 0,
    total: 0,
    etaSeconds: 0,
  });
  const [results, setResults] = useState<EnrichedDeal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const jobIdRef = useRef<string | null>(null);
  const intentionalClose = useRef(false);
  // Track how many results we had before reconnecting, so we can skip
  // duplicates when the server re-sends from the start
  const resultsBeforeReconnect = useRef(0);
  const resultsSeen = useRef(0);
  // Store last search params for retry
  const lastParamsRef = useRef<SearchRequest | null>(null);

  function connectWebSocket(jobId: string) {
    const wsUrl = getWebSocketUrl(jobId);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    resultsSeen.current = 0;

    ws.onmessage = (event) => {
      const msg: WSMessage = JSON.parse(event.data);
      // Successful message means we're connected — reset retry counter
      reconnectAttempts.current = 0;

      switch (msg.type) {
        case "status":
          setProgress((prev) => ({
            ...prev,
            step: msg.step,
            message: msg.message,
          }));
          break;

        case "progress":
          setProgress({
            step: msg.step,
            message: `Searching flights... (${msg.searched}/${msg.total})`,
            searched: msg.searched,
            total: msg.total,
            etaSeconds: msg.eta_seconds,
          });
          break;

        case "result":
          resultsSeen.current += 1;
          // On reconnect the server re-sends all results from the start.
          // Skip ones we already have.
          if (resultsSeen.current > resultsBeforeReconnect.current) {
            setResults((prev) => [...prev, msg.deal]);
          }
          break;

        case "complete":
          intentionalClose.current = true;
          setState("complete");
          ws.close();
          wsRef.current = null;
          jobIdRef.current = null;
          break;

        case "error":
          intentionalClose.current = true;
          setError(msg.message);
          // If we already have results, keep them visible with error_partial
          setResults((prev) => {
            if (prev.length > 0) {
              setState("error_partial");
            } else {
              setState("error");
            }
            return prev;
          });
          ws.close();
          wsRef.current = null;
          jobIdRef.current = null;
          break;

        // Ignore keepalive pings from the server
        case "ping":
          break;
      }
    };

    ws.onerror = () => {
      // Don't set error state here — let onclose handle reconnect
    };

    ws.onclose = () => {
      if (intentionalClose.current) {
        return;
      }

      // Unexpected close — try to reconnect
      if (
        jobIdRef.current &&
        reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS
      ) {
        reconnectAttempts.current += 1;
        const attempt = reconnectAttempts.current;
        setProgress((prev) => ({
          ...prev,
          message: `Connection lost, reconnecting (${attempt}/${MAX_RECONNECT_ATTEMPTS})...`,
        }));

        setTimeout(() => {
          // Only reconnect if we haven't been reset
          if (jobIdRef.current && !intentionalClose.current) {
            // Remember how many results we already have so we skip
            // duplicates when the server re-sends from the beginning
            setResults((prev) => {
              resultsBeforeReconnect.current = prev.length;
              return prev;
            });
            connectWebSocket(jobIdRef.current);
          }
        }, RECONNECT_DELAY_MS);
      } else {
        // Connection lost permanently — keep partial results if we have them
        setResults((prev) => {
          if (prev.length > 0) {
            setError("Connection lost. Your partial results are shown below.");
            setState("error_partial");
          } else {
            setError("Connection lost after multiple retries. Your partial results have been saved.");
            setState("error");
          }
          return prev;
        });
        jobIdRef.current = null;
      }
    };
  }

  const reset = useCallback(() => {
    intentionalClose.current = true;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    jobIdRef.current = null;
    reconnectAttempts.current = 0;
    intentionalClose.current = false;
    setState("idle");
    setResults([]);
    setProgress({ step: "", message: "", searched: 0, total: 0, etaSeconds: 0 });
    setError(null);
  }, []);

  const startSearch = useCallback(
    async (params: SearchRequest) => {
      // Clean up any existing connection
      intentionalClose.current = true;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      lastParamsRef.current = params;
      setState("searching");
      setResults([]);
      setError(null);
      reconnectAttempts.current = 0;
      resultsBeforeReconnect.current = 0;
      resultsSeen.current = 0;
      intentionalClose.current = false;
      setProgress({
        step: "starting",
        message: "Starting search...",
        searched: 0,
        total: 0,
        etaSeconds: 0,
      });

      try {
        const { job_id } = await createSearch(params);
        jobIdRef.current = job_id;
        connectWebSocket(job_id);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to start search"
        );
        setState("error");
      }
    },
    []
  );

  // Retry: start a new search with same params, keeping existing results visible
  const retrySearch = useCallback(async () => {
    const params = lastParamsRef.current;
    if (!params) return;

    // Clean up any existing connection
    intentionalClose.current = true;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setState("searching");
    setError(null);
    reconnectAttempts.current = 0;
    // Keep existing results — don't clear them
    // Set resultsBeforeReconnect so we skip duplicates
    setResults((prev) => {
      resultsBeforeReconnect.current = 0;
      resultsSeen.current = 0;
      return prev;
    });
    intentionalClose.current = false;
    setProgress({
      step: "starting",
      message: "Retrying search...",
      searched: 0,
      total: 0,
      etaSeconds: 0,
    });

    try {
      const { job_id } = await createSearch(params);
      jobIdRef.current = job_id;
      connectWebSocket(job_id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start search"
      );
      setResults((prev) => {
        if (prev.length > 0) {
          setState("error_partial");
        } else {
          setState("error");
        }
        return prev;
      });
    }
  }, []);

  return { state, progress, results, error, startSearch, retrySearch, reset };
}
