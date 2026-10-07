import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";

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

  test.each(["response", "body"])("displays config and preserves edits while history %s is pending", async (pendingStage) => {
    let finishHistory;
    const pendingHistory = new Promise(resolve => { finishHistory = resolve; });
    const history = [{ timestamp: "2026-10-05T12:00:00Z", data: "[shared]\nvalue=old\n" }];
    global.fetch = jest.fn((url) => {
      if (url === "/api/config/shared") {
        return Promise.resolve({ ok: true, text: async () => "[shared]\nvalue=global\n" });
      }
      if (url === "/api/config/shared/history") {
        return pendingStage === "response"
          ? pendingHistory
          : Promise.resolve({ ok: true, json: () => pendingHistory });
      }
      if (url === "/api/units") {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/config"]}>
        <EditConfig title="Pioreactor ~ Configuration" />
      </MemoryRouter>,
    );

    const editor = await screen.findByRole("textbox", { name: "Configuration editor" });
    expect(editor).toHaveValue("[shared]\nvalue=global\n");
    await userEvent.type(editor, "new-option=true");

    await act(async () => {
      finishHistory(pendingStage === "response" ? { ok: true, json: async () => history } : history);
    });

    expect(editor).toHaveValue("[shared]\nvalue=global\nnew-option=true");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await userEvent.click(screen.getByRole("combobox", { name: "Version:" }));
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  test.each(["http", "network"])("keeps config editable when history fails with a %s error", async (failure) => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    global.fetch = jest.fn((url) => {
      if (url === "/api/config/shared") {
        return Promise.resolve({ ok: true, text: async () => "[shared]\nvalue=global\n" });
      }
      if (url === "/api/config/shared/history") {
        return failure === "http"
          ? Promise.resolve({ ok: false })
          : Promise.reject(new Error("Network unavailable"));
      }
      if (url === "/api/units") {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/config"]}>
        <EditConfig title="Pioreactor ~ Configuration" />
      </MemoryRouter>,
    );

    const editor = await screen.findByRole("textbox", { name: "Configuration editor" });
    expect(editor).toHaveValue("[shared]\nvalue=global\n");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load config history.");
    await userEvent.type(editor, "new-option=true");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  test("ignores history from the previous target after switching configs", async () => {
    let finishSharedHistory;
    const pendingSharedHistory = new Promise(resolve => { finishSharedHistory = resolve; });
    global.fetch = jest.fn((url) => {
      if (url === "/api/config/shared") {
        return Promise.resolve({ ok: true, text: async () => "shared config" });
      }
      if (url === "/api/config/shared/history") {
        return pendingSharedHistory;
      }
      if (url === "/api/config/units/unit1/specific") {
        return Promise.resolve({ ok: true, text: async () => "unit config" });
      }
      if (url === "/api/config/units/unit1/specific/history") {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url === "/api/units") {
        return Promise.resolve({ ok: true, json: async () => [{ pioreactor_unit: "unit1" }] });
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/config"]}>
        <Routes>
          <Route path="/config/:pioreactorUnit?" element={<EditConfig title="Pioreactor ~ Configuration" />} />
        </Routes>
      </MemoryRouter>,
    );

    const editor = await screen.findByRole("textbox", { name: "Configuration editor" });
    await userEvent.click(screen.getByRole("combobox", { name: "Config target:" }));
    await userEvent.click(await screen.findByRole("option", { name: "unit1 unit config" }));
    await waitFor(() => expect(editor).toHaveValue("unit config"));
    await userEvent.type(editor, " edited");

    await act(async () => {
      finishSharedHistory({
        ok: true,
        json: async () => [{ timestamp: "2026-10-05T12:00:00Z", data: "old shared config" }],
      });
    });

    expect(editor).toHaveValue("unit config edited");
    await userEvent.click(screen.getByRole("combobox", { name: "Version:" }));
    expect(screen.getAllByRole("option")).toHaveLength(1);
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

  test("saves configuration with PUT without waiting for history", async () => {
    global.fetch = jest.fn((url, options = {}) => {
      if (url === "/api/config/shared" && options.method === "PUT") {
        return Promise.resolve({ ok: true });
      }

      if (url === "/api/config/shared") {
        return Promise.resolve({
          ok: true,
          text: async () => "[shared]\nvalue=global\n",
        });
      }

      if (url === "/api/config/shared/history") {
        return new Promise(() => {});
      }

      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/config"]}>
        <EditConfig title="Pioreactor ~ Configuration" />
      </MemoryRouter>,
    );

    const editor = await screen.findByRole("textbox", { name: "Configuration editor" });
    await userEvent.type(editor, "new-option=true");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/config/shared", {
        method: "PUT",
        body: JSON.stringify({ code: "[shared]\nvalue=global\nnew-option=true" }),
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      });
    });

    await waitFor(() => expect(editor).toHaveValue("[shared]\nvalue=global\n"));
    await userEvent.type(editor, "another-option=true");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });
});
