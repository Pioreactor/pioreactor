import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";

import EditConfig from "../EditConfig";

jest.mock("react-simple-code-editor", () => ({
  __esModule: true,
  default: ({ value, onValueChange }) => (
    <textarea
      aria-label="Configuration editor"
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
    />
  ),
}));

describe("EditConfig downloads", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("downloads all configuration INIs from the config archive endpoint", async () => {
    const archive = new Blob(["config archive"], { type: "application/zip" });
    global.fetch = jest.fn((url) => {
      if (url === "/api/config/shared") {
        return Promise.resolve({
          ok: true,
          text: async () => "[shared]\nvalue=global\n",
        });
      }

      if (url === "/api/config/shared/history") {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }

      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }

      if (url === "/api/config/zipped") {
        return Promise.resolve({
          ok: true,
          blob: async () => archive,
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    const createObjectURL = jest.fn(() => "blob:configuration");
    const revokeObjectURL = jest.fn();
    Object.defineProperty(window.URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(window.URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    });

    const originalCreateElement = document.createElement.bind(document);
    let downloadLink;
    jest.spyOn(document, "createElement").mockImplementation((tagName, options) => {
      const element = originalCreateElement(tagName, options);
      if (tagName === "a") {
        downloadLink = element;
      }
      return element;
    });
    jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(
      <MemoryRouter initialEntries={["/config"]}>
        <EditConfig title="Pioreactor ~ Configuration" />
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Download all configurations" }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/config/zipped");
      expect(downloadLink).toBeDefined();
      expect(downloadLink.getAttribute("download")).toBe("configuration_inis.zip");
      expect(downloadLink.getAttribute("href")).toBe("blob:configuration");
      expect(downloadLink.click).toHaveBeenCalled();
      expect(createObjectURL).toHaveBeenCalledWith(archive);
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:configuration");
    });
  });
});
