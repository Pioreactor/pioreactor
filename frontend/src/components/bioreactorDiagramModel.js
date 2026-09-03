const PIN_TO_PWM = {
  17: 1,
  13: 2,
  16: 3,
  12: 4,
  18: 5, // heater
};

export function getPwmDutyCyclesByLoad(dutyCyclesByPin, pwmConfig = {}) {
  const dutyCyclesByLoad = {};
  for (const [pin, dutyCycle] of Object.entries(dutyCyclesByPin)) {
    const load = pwmConfig[PIN_TO_PWM[pin]];
    if (load) {
      dutyCyclesByLoad[load] = Number(dutyCycle);
    }
  }
  return dutyCyclesByLoad;
}

export function getBioreactorTubeLayout({ bioreactor, size, volume, maxVolume, hasAirBubbler }) {
  const vialBottomY = bioreactor.y + bioreactor.height;
  const liquidHeight = (volume / size) * bioreactor.height;
  const liquidSurfaceY = vialBottomY - liquidHeight;
  const wasteTubeTipY = vialBottomY - (maxVolume / size) * bioreactor.height;
  const tubeTopY = bioreactor.y - 53;

  // A tube's load is its config identity, never its displayed label.
  const tubes = [
    { id: 'waste', label: 'efflux', load: 'waste', tipY: wasteTubeTipY },
    { id: 'media', label: 'media', load: 'media', tipY: tubeTopY + 100 },
    { id: 'alt_media', label: 'alt-media', load: 'alt_media', tipY: tubeTopY + 100 },
    {
      id: 'air',
      label: hasAirBubbler ? 'air-bubbler' : '',
      load: hasAirBubbler ? 'air_bubbler' : null,
      tipY: hasAirBubbler
        ? Math.min(liquidSurfaceY + 25, vialBottomY - 25)
        : tubeTopY + 100,
    },
  ].map((tube, index) => ({
    ...tube,
    x: bioreactor.x + (bioreactor.width * (4 - index)) / 5 - 10,
    y: tubeTopY,
    width: 20,
    radius: 3,
  }));

  if (hasAirBubbler) {
    const airTube = tubes.find(tube => tube.id === 'air');
    airTube.airStone = {
      x: airTube.x - 4,
      y: airTube.tipY - 4,
      width: airTube.width + 8,
      height: 40,
      radius: 5,
    };
  }

  return { liquidHeight, liquidSurfaceY, wasteTubeTipY, tubes };
}
