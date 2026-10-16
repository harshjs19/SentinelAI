import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useAsyncResource } from "./useAsyncResource";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((complete, fail) => { resolve = complete; reject = fail; });
  return { promise, resolve, reject };
}

describe("useAsyncResource", () => {
  it("ignores a late result from an aborted selection even when its loader ignores the signal", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const loadA = () => first.promise;
    const loadB = () => second.promise;
    const { result, rerender } = renderHook(({ loader }) => useAsyncResource(loader), {
      initialProps: { loader: loadA },
    });

    rerender({ loader: loadB });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);

    await act(async () => { second.resolve("Machine B history"); await second.promise; });
    expect(result.current.data).toBe("Machine B history");
    await act(async () => { first.resolve("Machine A history"); await first.promise; });
    expect(result.current.data).toBe("Machine B history");
    expect(result.current.error).toBeNull();
  });

  it("clears old data during a new selection, failure, and retry", async () => {
    let bCalls = 0;
    const loadA = () => Promise.resolve("Machine A history");
    const loadB = () => {
      bCalls += 1;
      return bCalls === 1
        ? Promise.reject<string>(new Error("B failed"))
        : Promise.resolve("Machine B history");
    };
    const { result, rerender } = renderHook(({ loader }) => useAsyncResource(loader), {
      initialProps: { loader: loadA },
    });
    await waitFor(() => expect(result.current.data).toBe("Machine A history"));

    rerender({ loader: loadB });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.error?.message).toBe("B failed"));
    expect(result.current.data).toBeNull();

    act(() => result.current.reload());
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    await waitFor(() => expect(result.current.data).toBe("Machine B history"));
    expect(bCalls).toBe(2);
  });

  it("does not surface a late failure from a superseded selection", async () => {
    const first = deferred<string>();
    const loadA = () => first.promise;
    const loadB = () => Promise.resolve("Machine B history");
    const { result, rerender } = renderHook(({ loader }) => useAsyncResource(loader), {
      initialProps: { loader: loadA },
    });

    rerender({ loader: loadB });
    await waitFor(() => expect(result.current.data).toBe("Machine B history"));
    await act(async () => {
      first.reject(new Error("Old machine failed"));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.data).toBe("Machine B history");
    expect(result.current.error).toBeNull();
  });
});
