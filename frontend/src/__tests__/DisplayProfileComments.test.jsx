import React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { DisplayProfile } = require("../components/DisplayProfile");
const {
  convertYamlToProfilePreview,
  getInlineCommentForPath,
} = require("../utils/experimentProfilePreview");

const profileYaml = `experiment_profile_name: Start fedbatch after batch

metadata:
  author: Stijn
  description: Custom fed-batch operation

common:
  jobs:
    dosing_automation:
      actions:
        - type: when
          t: 0.1 # start after 1h, for safety reasons
          wait_until: \${{::growth_rate_calculating:growth_rate.growth_rate > 0.1}}
          actions:
            - type: start
              t: 0.0
              options:
                automation_name: muset_fedbatch
                target_mu: 0.1 # 1/h
                dosing_volume: 0.01 # mL
                duration: 0.1 # min, time between checks
`;

describe("DisplayProfile comment rendering", () => {
  test("extracts inline comments for nested action fields", () => {
    const preview = convertYamlToProfilePreview(profileYaml);

    expect(getInlineCommentForPath(preview.comments, "common.jobs.dosing_automation.actions[0].t")).toBe(
      "start after 1h, for safety reasons",
    );
    expect(
      getInlineCommentForPath(
        preview.comments,
        "common.jobs.dosing_automation.actions[0].actions[0].options.target_mu",
      ),
    ).toBe("1/h");
    expect(
      getInlineCommentForPath(
        preview.comments,
        "common.jobs.dosing_automation.actions[0].actions[0].options.duration",
      ),
    ).toBe("min, time between checks");
  });

  test("shows extracted comments inline in the human-readable preview", () => {
    const preview = convertYamlToProfilePreview(profileYaml);

    render(<DisplayProfile data={preview.data} comments={preview.comments} />);

    expect(screen.getByText("#start after 1h, for safety reasons")).toBeInTheDocument();
    expect(screen.getByText("#1/h")).toBeInTheDocument();
    expect(screen.getByText("#mL")).toBeInTheDocument();
    expect(screen.getByText("#min, time between checks")).toBeInTheDocument();
  });
});
