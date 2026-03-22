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

  const reset = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setState("idle");
    setResults([]);
    setProgress({ step: "", message: "", searched: 0, total: 0, etaSeconds: 0 });
    setError(null);
  }, []);

  const startSearch = useCallback(
    async (params: SearchRequest) => {
      // Clean up any existing connection
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      setState("searching");
      setResults([]);
      setError(null);
      setProgress({
        step: "starting",
        message: "Starting search...",
        searched: 0,
        total: 0,
        etaSeconds: 0,
      });

      try {
        const { job_id } = await createSearch(params);

        const wsUrl = getWebSocketUrl(job_id);
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onmessage = (event) => {
          const msg: WSMessage = JSON.parse(event.data);

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
              setResults((prev) => [...prev, msg.deal]);
              break;

            case "complete":
              setState("complete");
              ws.close();
              wsRef.current = null;
              break;

            case "error":
              setError(msg.message);
              setState("error");
              ws.close();
              wsRef.current = null;
              break;
          }
        };

        ws.onerror = () => {
          setError("WebSocket connection error. Please try again.");
          setState("error");
        };

        ws.onclose = (event) => {
          // If we didn't already set complete/error state, treat as error
          setState((current) => {
            if (current === "searching") {
              if (!event.wasClean) {
                setError("Connection lost. Please try again.");
                return "error";
              }
            }
            return current;
          });
        };
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to start search"
        );
        setState("error");
      }
    },
    []
  );

  return { state, progress, results, error, startSearch, reset };
}
