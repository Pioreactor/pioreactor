import React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
import dayjs from "dayjs";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const CameraPanel = require("../components/CameraPanel").default;

describe("CameraPanel", () => {
  test("shows latest capture time since the experiment began with the timestamp in a tooltip", () => {
    render(
      <MemoryRouter>
        <CameraPanel
          unit="unit-1"
          experiment="experiment-a"
          experimentStartTime="2026-06-11T10:30:00Z"
          initialStatus={{
            available: true,
            latest_still: {
              image_id: "image-1",
              captured_at: "2026-06-11T12:00:00Z",
              experiment: "experiment-a",
            },
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("1.5 h")).toHaveAttribute(
      "aria-label",
      dayjs("2026-06-11T12:00:00Z").format("YYYY-MM-DD HH:mm:ss"),
    );
  });
});
