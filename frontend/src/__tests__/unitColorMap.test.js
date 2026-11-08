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
