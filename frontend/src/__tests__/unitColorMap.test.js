import { colors, createUnitColorMap } from "../utils/color";

test("units keep their usual colors when nothing is chosen", () => {
  const colorMap = createUnitColorMap(["unit1", "unit2", "unit3"]);
  expect([colorMap.unit1, colorMap.unit2, colorMap.unit3]).toEqual(colors.slice(0, 3));
});

test("a chosen color displaces only the unit whose usual color it took", () => {
  const colorMap = createUnitColorMap(["unit1", "unit2", "unit3", "unit4"], { unit4: colors[1] });
  expect(colorMap.unit1).toBe(colors[0]);
  expect(colorMap.unit2).toBe(colors[3]);
  expect(colorMap.unit3).toBe(colors[2]);
  expect(colorMap.unit4).toBe(colors[1]);
});

test("units seen later, like ones only in chart history, take unused colors", () => {
  const colorMap = createUnitColorMap(["unit1"], { old_unit: colors[1] });
  expect(colorMap.old_unit).toBe(colors[1]);
  expect(colorMap.unit9).toBe(colors[2]);
  expect(colorMap.unit9).toBe(colors[2]);
});

test.each([0, colors.length, colors.length + 5])(
  "cycles colors after palette exhaustion with %i units seeded initially",
  (seedCount) => {
    const units = Array.from({ length: colors.length * 2 + 3 }, (_, index) => `unit${index + 1}`);
    const colorMap = createUnitColorMap(units.slice(0, seedCount));

    units.forEach((unit, index) => {
      expect(colorMap[unit]).toBe(colors[index % colors.length]);
      expect(colorMap[unit]).toBe(colors[index % colors.length]);
    });
  },
);
