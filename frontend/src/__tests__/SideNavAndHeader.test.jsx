import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { pathnameMatchesAnySubmenu } = require("../components/SideNavAndHeader");

describe("pathnameMatchesAnySubmenu", () => {
  test("matches submenu routes directly from the current pathname", () => {
    expect(pathnameMatchesAnySubmenu("/leader", ["inventory", "leader", "system-logs"])).toBe(true);
    expect(pathnameMatchesAnySubmenu("/system-logs/unit-1", ["inventory", "leader", "system-logs"])).toBe(true);
    expect(pathnameMatchesAnySubmenu("/inventory", ["inventory", "leader", "system-logs"])).toBe(true);
  });

  test("does not open unrelated submenus", () => {
    expect(pathnameMatchesAnySubmenu("/overview", ["inventory", "leader", "system-logs"])).toBe(false);
    expect(pathnameMatchesAnySubmenu("/plugins", ["calibrations", "protocols", "estimators"])).toBe(false);
  });
});
