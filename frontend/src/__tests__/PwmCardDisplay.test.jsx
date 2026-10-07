import React from "react";
import { render } from "@testing-library/react";
import { UnitSettingDisplay } from "../components/PioreactorCardShared";

test("PWM card displays channel values and defaults omitted channels to zero", () => {
  const { container, getByText } = render(
    <UnitSettingDisplay
      value={JSON.stringify({ 1: 15, 4: 55, 5: 23.49 })}
      isUnitActive
      displayKind="pwm_dc"
      config={{ PWM: { 1: "stirring", 4: "media" } }}
      default="—"
    />,
  );

  expect(container).toHaveTextContent("1: 15%");
  expect(container).toHaveTextContent("2: 0%");
  expect(container).toHaveTextContent("3: 0%");
  expect(container).toHaveTextContent("4: 55%");
  expect(getByText("1")).toHaveAccessibleName("stirring");
  expect(getByText("4")).toHaveAccessibleName("media");
});
