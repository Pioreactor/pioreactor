import { byUnit, compareNatural, sortNatural } from "../utils/naturalSort";

test("unit names sort in natural order, ignoring case", () => {
  expect(["pio10", "Pio3", "pio2", "pio1"].sort(compareNatural)).toEqual(["pio1", "pio2", "Pio3", "pio10"]);
});

test("sortNatural sorts objects by key without mutating the input", () => {
  const workers = [{ pioreactor_unit: "w10" }, { pioreactor_unit: "w9" }];
  expect(sortNatural(workers, byUnit).map(byUnit)).toEqual(["w9", "w10"]);
  expect(workers.map(byUnit)).toEqual(["w10", "w9"]);
});
