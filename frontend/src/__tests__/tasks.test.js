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
