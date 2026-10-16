import { useCallback, useEffect, useState } from "react";

export interface AsyncResource<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

interface ResourceState<T> {
  loader: (signal: AbortSignal) => Promise<T>;
  revision: number;
  data: T | null;
  error: Error | null;
  loading: boolean;
}

export function useAsyncResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
): AsyncResource<T> {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({
    loader,
    revision,
    data: null,
    error: null,
    loading: true,
  });

  const reload = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setState({ loader, revision, data: null, error: null, loading: true });
    void loader(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setState({ loader, revision, data: value, error: null, loading: false });
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            loader,
            revision,
            data: null,
            error: reason instanceof Error ? reason : new Error("Request failed"),
            loading: false,
          });
        }
      });
    return () => controller.abort();
  }, [loader, revision]);

  const isCurrent = state.loader === loader && state.revision === revision;
  return {
    data: isCurrent ? state.data : null,
    error: isCurrent ? state.error : null,
    loading: !isCurrent || state.loading,
    reload,
  };
}

