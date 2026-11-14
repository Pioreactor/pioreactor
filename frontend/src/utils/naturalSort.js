// Natural order for unit names and labels: pio2 before pio10, case ignored.
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

export const compareNatural = collator.compare;

export const sortNatural = (items, key = (item) => item) =>
  [...items].sort((a, b) => compareNatural(key(a), key(b)));

export const byUnit = (worker) => worker.pioreactor_unit;
