import {
  buildBioreactorSettingsCollection,
  getBioreactorConfirmedValue,
  getBioreactorFallbackValue,
  getBioreactorSubscriptionTopics,
  mergeSettingsCollections,
  parseNumericValue,
} from "../utils/bioreactor";

describe("bioreactor utils", () => {
  test("parseNumericValue returns null for non-numeric values", () => {
    expect(parseNumericValue("12.5")).toBe(12.5);
    expect(parseNumericValue("")).toBeNull();
    expect(parseNumericValue("abc")).toBeNull();
  });

  test("getBioreactorFallbackValue reads mapped config values", () => {
    const config = {
      bioreactor: {
        initial_volume_ml: "11.5",
        efflux_tube_volume_ml: "18",
        initial_alt_media_fraction: "0.25",
        initial_cumulative_media_added_ml: "3",
      },
    };

    expect(getBioreactorFallbackValue(config, "current_volume_ml")).toBe(11.5);
    expect(getBioreactorFallbackValue(config, "efflux_tube_volume_ml")).toBe(18);
    expect(getBioreactorFallbackValue(config, "alt_media_fraction")).toBe(0.25);
    expect(getBioreactorFallbackValue(config, "cumulative_media_added_ml")).toBe(3);
  });

  test("getBioreactorFallbackValue prefers descriptor defaults", () => {
    const config = {
      bioreactor: {
        initial_cumulative_media_added_ml: "3",
      },
    };

    expect(
      getBioreactorFallbackValue(config, "cumulative_media_added_ml", {
        key: "cumulative_media_added_ml",
        default: 7,
      }),
    ).toBe(7);
  });

  test("getBioreactorConfirmedValue prefers confirmed values over config defaults", () => {
    const config = { bioreactor: { initial_volume_ml: "11.5" } };

    expect(getBioreactorConfirmedValue({ current_volume_ml: "13" }, config, "current_volume_ml")).toBe(13);
    expect(getBioreactorConfirmedValue({}, config, "current_volume_ml")).toBe(11.5);
    expect(
      getBioreactorConfirmedValue({}, config, {
        key: "cumulative_waste_removed_ml",
        default: 0,
      }),
    ).toBe(0);
  });

  test("buildBioreactorSettingsCollection builds a displayable settings collection", () => {
    const collection = buildBioreactorSettingsCollection(
      [
        {
          key: "current_volume_ml",
          label: "Current volume",
          type: "numeric",
          unit: "mL",
          min: 0,
          max: null,
          display: true,
          editable: true,
          default: 10,
        },
      ],
      {},
      {},
      { reactor_max_fill_volume_ml: 40 },
    );

    expect(collection.metadata.display).toBe(true);
    expect(collection.publishedSettings.current_volume_ml.value).toBe(10);
    expect(collection.publishedSettings.current_volume_ml.max).toBe(40);
  });

  test("mergeSettingsCollections adds bioreactor only when present", () => {
    const jobs = { stirring: { publishedSettings: {} } };
    const passiveSettingsCollections = { leds: { publishedSettings: {} } };
    const bioreactorSettingsCollection = { publishedSettings: {} };

    expect(mergeSettingsCollections(jobs, passiveSettingsCollections, null)).toEqual({
      stirring: jobs.stirring,
      leds: passiveSettingsCollections.leds,
    });
    expect(mergeSettingsCollections(jobs, passiveSettingsCollections, bioreactorSettingsCollection)).toEqual({
      stirring: jobs.stirring,
      leds: passiveSettingsCollections.leds,
      bioreactor: bioreactorSettingsCollection,
    });
  });

  test("getBioreactorSubscriptionTopics includes canonical testing experiment topics by default", () => {
    expect(getBioreactorSubscriptionTopics("unit1", "exp1")).toEqual([
      "pioreactor/unit1/exp1/bioreactor/current_volume_ml",
      "pioreactor/unit1/exp1/bioreactor/efflux_tube_volume_ml",
      "pioreactor/unit1/exp1/bioreactor/alt_media_fraction",
      "pioreactor/unit1/exp1/bioreactor/cumulative_media_added_ml",
      "pioreactor/unit1/exp1/bioreactor/cumulative_alt_media_added_ml",
      "pioreactor/unit1/exp1/bioreactor/cumulative_waste_removed_ml",
      "pioreactor/unit1/_testing_exp1/bioreactor/current_volume_ml",
      "pioreactor/unit1/_testing_exp1/bioreactor/efflux_tube_volume_ml",
      "pioreactor/unit1/_testing_exp1/bioreactor/alt_media_fraction",
      "pioreactor/unit1/_testing_exp1/bioreactor/cumulative_media_added_ml",
      "pioreactor/unit1/_testing_exp1/bioreactor/cumulative_alt_media_added_ml",
      "pioreactor/unit1/_testing_exp1/bioreactor/cumulative_waste_removed_ml",
    ]);
  });

  test("getBioreactorSubscriptionTopics can subscribe from descriptor keys", () => {
    expect(
      getBioreactorSubscriptionTopics("unit1", "exp1", [
        "cumulative_media_added_ml",
        "current_volume_ml",
        "cumulative_media_added_ml",
      ]),
    ).toEqual([
      "pioreactor/unit1/exp1/bioreactor/cumulative_media_added_ml",
      "pioreactor/unit1/exp1/bioreactor/current_volume_ml",
      "pioreactor/unit1/_testing_exp1/bioreactor/cumulative_media_added_ml",
      "pioreactor/unit1/_testing_exp1/bioreactor/current_volume_ml",
    ]);
  });
});
