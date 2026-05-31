import { experimentPathSegment } from "../utils/url";

describe("URL utils", () => {
  test("encodes an experiment name before it is inserted into an API path", () => {
    expect(experimentPathSegment("trial ? A")).toBe("trial%20%3F%20A");
  });
});
