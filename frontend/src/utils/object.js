export function objectWithDefaultEmpty(obj) {
  return new Proxy(obj, {
    get(target, key) {
      if (key in target) {
        return target[key];
      }
      return {};
    },
  });
}
