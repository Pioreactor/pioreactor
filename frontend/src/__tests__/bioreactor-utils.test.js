import {
  getBioreactorDescriptors,
  resetBioreactorDescriptorsCache,
} from "../utils/bioreactor";

describe("bioreactor utils", () => {
  beforeEach(() => {
    resetBioreactorDescriptorsCache();
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("getBioreactorDescriptors caches the shared descriptors request", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([{ key: "current_volume_ml" }]),
    });

    const first = await getBioreactorDescriptors();
    const second = await getBioreactorDescriptors();

    expect(first).toEqual([{ key: "current_volume_ml" }]);
    expect(second).toEqual(first);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith("/api/bioreactor/descriptors");
  });

  test("getBioreactorDescriptors resets the cache after a failure", async () => {
    global.fetch
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([{ key: "efflux_tube_volume_ml" }]),
      });

    await expect(getBioreactorDescriptors()).rejects.toThrow("HTTP error! Status: 500");

    const descriptors = await getBioreactorDescriptors();

    expect(descriptors).toEqual([{ key: "efflux_tube_volume_ml" }]);
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});
