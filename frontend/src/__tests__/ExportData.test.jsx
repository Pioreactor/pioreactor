import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../utils/tasks", () => ({
  fetchTaskResult: jest.fn(),
}));

const { MemoryRouter, Route, Routes } = require("react-router");
const { fetchTaskResult } = require("../utils/tasks");
const ExportData = require("../ExportData").default;

function renderExportData(initialEntry = "/export-data") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/export-data" element={<ExportData title="Pioreactor ~ Export data" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ExportData", () => {
  let consoleErrorSpy;

  beforeEach(() => {
    consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    fetchTaskResult.mockReset();

    global.fetch = jest.fn((url) => {
      if (url === "/api/experiments") {
        return Promise.resolve({
          ok: true,
          json: async () => [{ experiment: "exp-1" }],
        });
      }

      if (url === "/api/datasets/exportable") {
        return Promise.resolve({
          ok: false,
          status: 400,
          json: async () => ({ error: "Could not read exportable datasets." }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("shows the API error when exportable datasets fail to load", async () => {
    renderExportData();

    expect(await screen.findByText("Could not read exportable datasets.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^export$/i })).toBeDisabled();
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  test("preserves a comma-containing experiment from the URL", async () => {
    global.fetch = jest.fn((url) => {
      if (url === "/api/experiments") {
        return Promise.resolve({
          ok: true,
          json: async () => [{ experiment: "E coli, 37C" }],
        });
      }

      if (url === "/api/datasets/exportable") {
        return Promise.resolve({
          ok: false,
          status: 400,
          json: async () => ({ error: "Could not read exportable datasets." }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    renderExportData("/export-data?experiments=E%20coli%2C%2037C");

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toHaveTextContent("E coli, 37C");
    });
  });

  test("shows a durable success alert when USB export completes", async () => {
    global.fetch = jest.fn((url) => {
      if (url === "/api/experiments") {
        return Promise.resolve({
          ok: true,
          json: async () => [{ experiment: "exp-1" }],
        });
      }

      if (url === "/api/datasets/exportable") {
        return Promise.resolve({
          ok: true,
          json: async () => [
            {
              dataset_name: "od_readings",
              display_name: "OD readings",
              description: "Optical density readings.",
              source: "app",
            },
          ],
        });
      }

      if (url === "/unit_api/usb") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ active_mount: { writable: true } }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
    fetchTaskResult.mockResolvedValue({ result: { filename: "export.zip" } });

    renderExportData();

    fireEvent.mouseDown(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "exp-1" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "OD readings" }));

    const selectButtonParts = await screen.findAllByRole("button");
    fireEvent.click(selectButtonParts[1]);
    fireEvent.click(await screen.findByRole("option", { name: "Export to USB" }));
    fireEvent.click(screen.getByRole("button", { name: "Export to USB" }));

    expect(await screen.findByText("Export saved to USB as export.zip.")).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/datasets/exportable/export-to-usb",
        expect.objectContaining({
          fetchOptions: expect.objectContaining({ method: "POST" }),
        }),
      );
    });
  });

  test("downloads a completed browser export with the returned filename", async () => {
    global.fetch = jest.fn((url) => {
      if (url === "/api/experiments") {
        return Promise.resolve({
          ok: true,
          json: async () => [{ experiment: "exp-1" }],
        });
      }

      if (url === "/api/datasets/exportable") {
        return Promise.resolve({
          ok: true,
          json: async () => [
            {
              dataset_name: "od_readings",
              display_name: "OD readings",
              description: "Optical density readings.",
              source: "app",
            },
          ],
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
    const filename = "export 100% & ready.zip";
    fetchTaskResult.mockResolvedValue({ result: { filename } });
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

    renderExportData();

    fireEvent.mouseDown(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "exp-1" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "OD readings" }));
    fireEvent.click(screen.getByRole("button", { name: /^export 1$/i }));

    await waitFor(() => {
      expect(downloadLink).toBeDefined();
      expect(downloadLink.getAttribute("download")).toBe(filename);
      expect(downloadLink.getAttribute("href")).toBe("/exports/export%20100%25%20%26%20ready.zip");
      expect(downloadLink.click).toHaveBeenCalled();
    });
  });
});
