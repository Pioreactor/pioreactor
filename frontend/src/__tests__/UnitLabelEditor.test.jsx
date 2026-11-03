import React, { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import UnitLabelEditor from "../components/UnitLabelEditor";

function Harness({ initialLabel = "" }) {
  const [label, setLabel] = useState(initialLabel);
  return <UnitLabelEditor unit="unit-1" experiment="exp 1" label={label} onLabelChange={setLabel} />;
}

function okResponse() {
  return Promise.resolve({ ok: true, json: async () => ({ status: "success" }) });
}

describe("UnitLabelEditor", () => {
  beforeEach(() => {
    global.fetch = jest.fn(okResponse);
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("adds a label with Enter", async () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Add label for unit-1" }));
    const input = screen.getByRole("textbox", { name: "Label for unit-1" });
    fireEvent.change(input, { target: { value: "  Strain A  " } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(await screen.findByText("Strain A")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/api/experiments/exp%201/unit_labels");
    expect(options.method).toBe("PUT");
    expect(JSON.parse(options.body)).toEqual({ unit: "unit-1", label: "Strain A" });
  });

  test("saves on blur and removes the label when emptied", async () => {
    render(<Harness initialLabel="Strain A" />);

    fireEvent.click(screen.getByRole("button", { name: "Edit label for unit-1" }));
    const input = screen.getByRole("textbox", { name: "Label for unit-1" });
    expect(input).toHaveValue("Strain A");
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);

    expect(await screen.findByText("unit-1")).toBeInTheDocument();
    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({ unit: "unit-1", label: "" });
  });

  test("Escape cancels without saving", () => {
    render(<Harness initialLabel="Strain A" />);

    fireEvent.click(screen.getByRole("button", { name: "Edit label for unit-1" }));
    const input = screen.getByRole("textbox", { name: "Label for unit-1" });
    fireEvent.change(input, { target: { value: "Strain B" } });
    fireEvent.keyDown(input, { key: "Escape" });
    fireEvent.blur(input);

    expect(screen.getByText("Strain A")).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test("keeps the field open and shows the server error", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: false,
        json: async () => ({ error: "`unit-2` already uses the label `Strain A` in this experiment." }),
      }),
    );
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Add label for unit-1" }));
    const input = screen.getByRole("textbox", { name: "Label for unit-1" });
    fireEvent.change(input, { target: { value: "Strain A" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(await screen.findByText("unit-2 already uses the label Strain A in this experiment.")).toBeInTheDocument();
    await waitFor(() => expect(input).not.toBeDisabled());
    expect(input).toHaveValue("Strain A");
  });
});
