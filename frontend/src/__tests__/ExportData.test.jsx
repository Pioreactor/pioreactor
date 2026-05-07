import React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter, Route, Routes } = require("react-router");
const ExportData = require("../ExportData").default;

function renderExportData() {
  return render(
    <MemoryRouter initialEntries={["/export-data"]}>
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
});
