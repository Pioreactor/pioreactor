import { checkTaskCallback, TaskPollingTimeoutError } from "../utils/tasks";

afterEach(() => {
  jest.restoreAllMocks();
  jest.useRealTimers();
});

test("pending tasks exhaust polling without reporting task failure", async () => {
  jest.useFakeTimers();
  global.fetch = jest.fn().mockResolvedValue({ status: 202 });

  const result = checkTaskCallback("/unit_api/task_results/pending", { maxRetries: 2, delayMs: 200 });
  const assertion = expect(result).rejects.toBeInstanceOf(TaskPollingTimeoutError);
  await jest.runAllTimersAsync();
  await assertion;
  expect(fetch).toHaveBeenCalledTimes(2);
});

test("polling starts quickly and backs off to delayMs", async () => {
  jest.useFakeTimers();
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ status: 202 })
    .mockResolvedValueOnce({ status: 202 })
    .mockResolvedValueOnce({ status: 202 })
    .mockResolvedValue({ status: 200, ok: true, json: async () => ({ status: "succeeded", result: 1 }) });

  const result = checkTaskCallback("/unit_api/task_results/quick", { maxRetries: 10, delayMs: 100 });
  await jest.advanceTimersByTimeAsync(0);
  expect(fetch).toHaveBeenCalledTimes(1);
  await jest.advanceTimersByTimeAsync(25);
  expect(fetch).toHaveBeenCalledTimes(2);
  await jest.advanceTimersByTimeAsync(50);
  expect(fetch).toHaveBeenCalledTimes(3);
  await jest.advanceTimersByTimeAsync(99);
  expect(fetch).toHaveBeenCalledTimes(3);
  await jest.advanceTimersByTimeAsync(1);
  await expect(result).resolves.toEqual({ status: "succeeded", result: 1 });
  expect(fetch).toHaveBeenCalledTimes(4);
});

test("terminal lock failures preserve the server error and stop polling", async () => {
  const error = "Another experiment deletion is in progress. Wait for it to finish, then try again.";
  global.fetch = jest.fn().mockResolvedValue({
    status: 200,
    ok: true,
    json: async () => ({ status: "failed", error }),
  });

  await expect(checkTaskCallback("/unit_api/task_results/locked")).rejects.toThrow(error);
  expect(fetch).toHaveBeenCalledTimes(1);
});
