import { useCallback, useEffect, useState } from "react";

export type Loaded<T> =
  | { state: "loading" }
  | { state: "failed"; error: unknown }
  | { state: "ready"; value: T; reload: () => Promise<void> };

/** Runs `load` when `key` changes; `reload` runs it again in place, without going back to the loading state. */
export function useLoaded<T>(key: string, load: () => Promise<T>): Loaded<T> {
  const [result, setResult] = useState<{ key: string; value?: T; error?: unknown }>();
  // `load` is keyed by `key`: a new function for the same key is the same request.
  const run = useCallback(load, [key]);
  const reload = useCallback(async () => {
    try {
      setResult({ key, value: await run() });
    } catch (error) {
      setResult({ key, error });
    }
  }, [key, run]);
  useEffect(() => {
    let current = true;
    run().then(
      (value) => current && setResult({ key, value }),
      (error: unknown) => current && setResult({ key, error }),
    );
    return () => {
      current = false;
    };
  }, [key, run]);
  if (!result || result.key !== key) return { state: "loading" };
  if ("error" in result && result.error !== undefined) return { state: "failed", error: result.error };
  return { state: "ready", value: result.value as T, reload };
}
