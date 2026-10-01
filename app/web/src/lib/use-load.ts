"use client";

import { useEffect, useState } from "react";

export function useLoad<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!path) return;
    let cancel = false;
    let done = false;
    const timer = window.setTimeout(() => {
      if (!cancel) setLoading(true);
    }, 300);
    const clear = window.setTimeout(() => {
      if (!cancel && !done) {
        setData(null);
        setError(false);
      }
    }, 0);
    fetch(path)
      .then(async (response) => {
        if (!response.ok) throw new Error("bad");
        return response.json() as Promise<T>;
      })
      .then((body) => {
        if (cancel) return;
        done = true;
        window.clearTimeout(timer);
        window.clearTimeout(clear);
        setData(body);
        setLoading(false);
      })
      .catch(() => {
        if (cancel) return;
        done = true;
        window.clearTimeout(timer);
        window.clearTimeout(clear);
        setData(null);
        setError(true);
        setLoading(false);
      });
    return () => {
      cancel = true;
      window.clearTimeout(timer);
      window.clearTimeout(clear);
    };
  }, [path, tick]);

  return { data, error, loading, retry: () => setTick((value) => value + 1) };
}
