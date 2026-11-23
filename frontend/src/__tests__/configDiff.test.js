import { diffConfigs, parseIni } from "../utils/configDiff";

describe("parseIni", () => {
  test("reads sections, both delimiters, continuations, and ignores comments", () => {
    const sections = parseIni([
      "# leading comment",
      "[stirring.config]",
      "target_rpm = 500",
      "; another comment",
      "pwm_hz: 200",
      "[PWM]",
      "1=stirring",
      "description=first line",
      "    second line",
    ].join("\n"));

    expect([...sections.keys()]).toEqual(["stirring.config", "PWM"]);
    expect(sections.get("stirring.config").get("target_rpm")).toBe("500");
    expect(sections.get("stirring.config").get("pwm_hz")).toBe("200");
    expect(sections.get("PWM").get("description")).toBe("first line\nsecond line");
  });
});

describe("diffConfigs", () => {
  test("reports changed, added, and removed keys in file order", () => {
    const saved = "[a]\nx=1\ny=2\nz=3\n";
    const edited = "[a]\nx=1\ny=20\nw=4\n";

    expect(diffConfigs(saved, edited)).toEqual([
      {
        name: "a",
        status: "changed",
        entries: [
          { key: "y", status: "changed", oldValue: "2", newValue: "20" },
          { key: "z", status: "removed", oldValue: "3" },
          { key: "w", status: "added", newValue: "4" },
        ],
      },
    ]);
  });

  test("reports added and removed sections and skips unchanged ones", () => {
    const saved = "[keep]\nx=1\n[gone]\ny=2\n";
    const edited = "[keep]\nx=1\n[new]\nz=3\n";

    expect(diffConfigs(saved, edited)).toEqual([
      { name: "gone", status: "removed", entries: [{ key: "y", status: "removed", oldValue: "2" }] },
      { name: "new", status: "added", entries: [{ key: "z", status: "added", newValue: "3" }] },
    ]);
  });

  test("ignores comment and whitespace-only edits", () => {
    expect(diffConfigs("[a]\nx=1\n", "# note\n[a]\nx = 1\n\n")).toEqual([]);
  });
});
