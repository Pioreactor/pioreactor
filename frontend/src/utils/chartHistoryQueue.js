// Batch charts mounted in one render so their layout, rather than effect order,
// determines which histories compete for the leader and the browser.
export function createChartHistoryQueue() {
  const pending = new Set();
  let scheduled = false;
  let running = false;

  function schedule() {
    if (scheduled || running || !pending.size) return;
    scheduled = true;
    requestAnimationFrame(async () => {
      scheduled = false;
      const visible = [...pending].filter(({ element }) => {
        const { top, bottom } = element.getBoundingClientRect();
        return bottom > 0 && top < window.innerHeight;
      });
      const batch = visible.length ? visible : [...pending];
      running = true;
      for (const entry of batch) pending.delete(entry);
      await Promise.allSettled(batch.map(({ load }) => load()));
      running = false;
      schedule();
    });
  }

  return (element, load) => {
    const entry = { element, load };
    pending.add(entry);
    schedule();
    return () => pending.delete(entry);
  };
}
