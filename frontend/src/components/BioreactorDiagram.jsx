import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import Box from '@mui/material/Box';
import { uiColors } from '../theme/colors';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useMQTT } from '../providers/MQTTContext';
import { getBioreactorTubeLayout, getPwmDutyCyclesByLoad } from './bioreactorDiagramModel';

function roundTo1(x) {
  return `${Math.round(x * 10) / 10}`;
}

function pseudoRandom(x, y) {
  return Math.abs(Math.sin(x * 976.34 + y)) % 1;
}

function binFloat(value, binSize) {
  return Math.floor(value / binSize) * binSize;
}

const versionMap = {
  20: {
    diagramDim: { width: 400, height: 510 },
    bioreactorHeight: 400,
    stirBarOffset: 160,
    frameFactor: 200,
    rpmClampMax: 600,
    baseLow: 320,
    baseHigh: 455,
  },
  40: {
    diagramDim: { width: 400, height: 610 },
    bioreactorHeight: 500,
    stirBarOffset: 210,
    frameFactor: 130,
    rpmClampMax: 800,
    baseLow: 420,
    baseHigh: 555,
  },
};

function clampVolume(value, fallbackValue, size) {
  const parsedValue = parseFloat(value);
  if (Number.isFinite(parsedValue)) {
    return Math.min(parsedValue, size);
  }
  return Math.min(fallbackValue, size);
}

const BioreactorDiagram = ({ experiment, unit, config, size, liquidVolume, maxVolume }) => {
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();

  const {
    diagramDim,
    bioreactorHeight,
    stirBarOffset,
    frameFactor,
    rpmClampMax,
    baseLow,
    baseHigh,
  } = versionMap[size] || versionMap[20];
  const diagramYOffset = 30;
  const shiftedBaseLow = baseLow + diagramYOffset;
  const shiftedBaseHigh = baseHigh + diagramYOffset;

  const bioreactor = useMemo(() => ({
    width: 200,
    height: bioreactorHeight,
    x: (diagramDim.width - 200) / 2,
    y: (diagramDim.height - bioreactorHeight) / 2 - 20 + diagramYOffset,
    cornerRadius: 20,
    stirBar: {
      maxWidth: 70,
      height: 10,
      x: (diagramDim.width - 70) / 2,
      y: (diagramDim.height - 10) / 2 + stirBarOffset + diagramYOffset,
      radius: 3,
    },
  }), [bioreactorHeight, diagramDim.height, diagramDim.width, diagramYOffset, stirBarOffset]);
  const cap = {
    width: bioreactor.width * 0.95,
    height: 52,
    x: bioreactor.x + 5,
    y: bioreactor.y - 63,
    radius: 3,
  };

  const stirBarRef = useRef(null);
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const [dutyCyclesByPin, setDutyCyclesByPin] = useState({});
  const [temperature, setTemperature] = useState(null);
  const [nOD, setNOD] = useState(null);
  const [leds, setLeds] = useState({ A: 0, B: 0, C: 0, D: 0 });
  const pwmConfig = config?.PWM;
  const dutyCyclesByLoad = useMemo(
    () => getPwmDutyCyclesByLoad(dutyCyclesByPin, pwmConfig),
    [dutyCyclesByPin, pwmConfig],
  );
  const rpmEstimate = dutyCyclesByLoad.stirring * 26.66666667;
  const rpm = Number.isFinite(rpmEstimate) && rpmEstimate > 0
    ? Math.min(Math.max(rpmEstimate, 100), rpmClampMax)
    : 0;
  const heat = dutyCyclesByLoad.heating > 0;
  const liquidPumpActive = ['media', 'alt_media', 'waste'].some(load => dutyCyclesByLoad[load] > 0);

  const defaultVolume = size === 20 ? 14 : 20;
  const volume = clampVolume(
    liquidVolume ?? config?.bioreactor?.initial_volume_ml,
    defaultVolume,
    size,
  );
  const cappedMaxVolume = clampVolume(
    maxVolume ?? config?.bioreactor?.efflux_tube_volume_ml,
    size,
    size,
  );
  const { liquidHeight, liquidSurfaceY, wasteTubeTipY, tubes } = useMemo(() => {
    const layout = getBioreactorTubeLayout({
      bioreactor,
      size,
      volume,
      maxVolume: cappedMaxVolume,
      pwmConfig,
    });
    return {
      ...layout,
      tubes: layout.tubes.map(tube => ({ ...tube, active: dutyCyclesByLoad[tube.load] > 0 })),
    };
  }, [bioreactor, size, volume, cappedMaxVolume, dutyCyclesByLoad, pwmConfig]);

  const onMessage = useCallback((topic, message) => {
    if (!message || !topic) return;

    const topicString = topic.toString();
    const messageString = message.toString();

    if (topicString.endsWith('pwms/dc')) {
      setDutyCyclesByPin(messageString ? JSON.parse(messageString) : {});
    } else if (topicString.endsWith('temperature_automation/temperature')) {
      setTemperature(messageString ? JSON.parse(messageString).temperature : null);
    } else if (topicString.endsWith('growth_rate_calculating/od_filtered')) {
      setNOD(messageString ? JSON.parse(messageString).od_filtered : null);
    } else if (topicString.endsWith('leds/intensity')) {
      setLeds(messageString ? JSON.parse(messageString) : { A: 0, B: 0, C: 0, D: 0 });
    }
  }, []);

  useEffect(() => {
    if (!client || !experiment || !config || Object.keys(config).length === 0) {
      return undefined;
    }
    const topics = [
      `pioreactor/${unit}/${experiment}/temperature_automation/temperature`,
      `pioreactor/${unit}/${experiment}/growth_rate_calculating/od_filtered`,
      `pioreactor/${unit}/${experiment}/leds/intensity`,
      `pioreactor/${unit}/${experiment}/pwms/dc`,
      `pioreactor/${unit}/_testing_${experiment}/temperature_automation/temperature`,
      `pioreactor/${unit}/_testing_${experiment}/growth_rate_calculating/od_filtered`,
      `pioreactor/${unit}/_testing_${experiment}/leds/intensity`,
      `pioreactor/${unit}/_testing_${experiment}/pwms/dc`,
    ];
    subscribeToTopic(topics, onMessage, 'BioreactorDiagram');
    return () => {
      unsubscribeFromTopic(topics, 'BioreactorDiagram');
    };
  }, [client, config, experiment, onMessage, subscribeToTopic, unsubscribeFromTopic, unit]);

  // Only the stir bar changes each frame; telemetry and geometry render through React.
  useEffect(() => {
    const stirBar = stirBarRef.current;
    const centerX = bioreactor.stirBar.x + bioreactor.stirBar.maxWidth / 2;
    const restingWidth = bioreactor.stirBar.maxWidth + 10;
    stirBar.setAttribute('width', restingWidth);
    stirBar.setAttribute('x', centerX - restingWidth / 2);
    if (rpm === 0 || prefersReducedMotion) return undefined;

    let animationFrameId;
    let startedAt;
    function animateStirBar(timestamp) {
      startedAt ??= timestamp;
      const angle = 2 * Math.PI * (timestamp - startedAt) * rpm / (1000 * frameFactor);
      const width = bioreactor.stirBar.maxWidth * Math.abs(Math.cos(angle)) + 10;
      stirBar.setAttribute('width', width);
      stirBar.setAttribute('x', centerX - width / 2);
      animationFrameId = window.requestAnimationFrame(animateStirBar);
    }
    animationFrameId = window.requestAnimationFrame(animateStirBar);
    return () => window.cancelAnimationFrame(animationFrameId);
  }, [bioreactor.stirBar, frameFactor, prefersReducedMotion, rpm]);

  const liquidY = Math.max(liquidSurfaceY, bioreactor.y);
  const visibleLiquidHeight = Math.min(liquidHeight, bioreactor.height);
  const liquidWaves = useMemo(() => {
    const paths = [];
    if (!nOD || visibleLiquidHeight <= 0) return paths;
    const waveSpacing = 150 / binFloat(nOD, 0.1);
    if (waveSpacing <= 0) return paths;
    for (let y = liquidY + 10; y < liquidY + visibleLiquidHeight; y += waveSpacing) {
      const r = pseudoRandom(pseudoRandom(y, 0.618), pseudoRandom(y, 1.618));
      const points = [];
      for (let x = bioreactor.x; x <= bioreactor.x + bioreactor.width; x += 10) {
        points.push(`${x},${y + Math.sin((1 + r) * (x / 10)) * 5}`);
      }
      paths.push(points.join(' '));
    }
    return paths;
  }, [bioreactor.width, bioreactor.x, liquidY, nOD, visibleLiquidHeight]);

  const ledY = shiftedBaseLow - 20;
  const ledRects = [
    { label: 'B', x: 50, y: ledY + 50 },
    { label: 'D', x: 310, y: ledY + 50 },
    { label: 'A', x: 50, y: ledY },
    { label: 'C', x: 310, y: ledY },
  ];
  const dynamicRects = [];
  if (temperature) {
    dynamicRects.push({ text: `Temp: ${roundTo1(temperature)}°C`, x: 110, width: 90 });
  }
  if (nOD) {
    dynamicRects.push({ text: `nOD: ${roundTo1(nOD)}`, x: 210, width: 80 });
  }
  const effluxLabelOnLiquid = visibleLiquidHeight > 0
    && wasteTubeTipY + 23 >= liquidY
    && wasteTubeTipY + 23 <= liquidY + visibleLiquidHeight;
  const volumeLabelY = Math.max(liquidSurfaceY - 30, 40);
  const outlineTop = (diagramDim.height - bioreactor.height) / 2 + diagramYOffset - 50;

  return (
    <Box
      component="svg"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Bioreactor diagram"
      viewBox={`0 0 ${diagramDim.width} ${diagramDim.height}`}
      width={diagramDim.width}
      height={diagramDim.height}
      sx={(theme) => ({
        display: 'block', m: '0 auto', maxWidth: '100%', height: 'auto',
        '--diagram-surface': '#fff',
        '--diagram-ink': '#000',
        '--diagram-muted': 'grey',
        '--diagram-liquid-text': 'grey',
        '--diagram-vial': 'rgb(244,244,244)',
        '--diagram-frame': 'rgba(0,0,0,0.01)',
        '--diagram-frame-outline': 'rgba(0,0,0,0.04)',
        '--diagram-cap': '#ececed',
        '--diagram-cap-outline': '#E0E0E1',
        ...theme.applyStyles('dark', {
          '--diagram-surface': uiColors.subtleBackground,
          '--diagram-ink': uiColors.text,
          '--diagram-muted': uiColors.textSecondary,
          '--diagram-liquid-text': '#58534b',
          '--diagram-vial': uiColors.surface,
          '--diagram-frame': 'rgba(255,255,255,0.02)',
          '--diagram-frame-outline': 'rgba(255,255,255,0.08)',
          '--diagram-cap': '#41424d',
          '--diagram-cap-outline': '#55535f',
        }),
      })}
      fill="var(--diagram-surface)"
      stroke="var(--diagram-ink)"
      strokeWidth={3}
      fontFamily="Roboto, sans-serif"
      fontSize={13}
      textAnchor="middle"
      dominantBaseline="central"
    >
      <desc>
        {`${roundTo1(volume)} mL liquid; efflux tube level ${roundTo1(cappedMaxVolume)} mL. `}
        {`Stirring ${rpm > 0 ? 'on' : 'off'}. Heating ${heat ? 'on' : 'off'}.`}
      </desc>
      <path
        d={`M 70 ${outlineTop} V ${shiftedBaseLow - 50} H 20 V ${shiftedBaseHigh - 50}
          H 55 V ${diagramDim.height - 30 + diagramYOffset} H ${diagramDim.width - 55}
          V ${shiftedBaseHigh - 50} H ${diagramDim.width - 20} V ${shiftedBaseLow - 50}
          H ${diagramDim.width - 70} V ${outlineTop} Z`}
        fill="var(--diagram-frame)"
        stroke="var(--diagram-frame-outline)"
        strokeWidth={8}
      />
      <rect
        x={bioreactor.x} y={bioreactor.y} width={bioreactor.width}
        height={bioreactor.height} rx={bioreactor.cornerRadius} fill="var(--diagram-vial)"
      />
      {visibleLiquidHeight > 0 && (
        <g>
          <rect
            x={bioreactor.x} y={liquidY} width={bioreactor.width}
            height={visibleLiquidHeight} rx={10} fill="#e0d0b5"
          />
          {liquidWaves.map((points, index) => (
            <polyline key={index} points={points} fill="none" stroke="#e0d0b540" strokeWidth={1} />
          ))}
        </g>
      )}
      <line
        x1={bioreactor.x + 2} x2={bioreactor.x + bioreactor.width - 2}
        y1={wasteTubeTipY} y2={wasteTubeTipY} stroke="var(--diagram-muted)" strokeWidth={1} strokeDasharray="4 3"
      />
      <text
        x={bioreactor.x + bioreactor.width / 2 + 60} y={wasteTubeTipY + 23}
        fill={effluxLabelOnLiquid ? "var(--diagram-liquid-text)" : "var(--diagram-muted)"} stroke="none" fontSize={12} dominantBaseline="text-after-edge"
      >
        {roundTo1(cappedMaxVolume)} mL
      </text>
      <rect
        x={cap.x} y={cap.y} width={cap.width} height={cap.height} rx={cap.radius}
        fill="var(--diagram-cap)" stroke="var(--diagram-cap-outline)" strokeWidth={6}
      />
      <rect
        ref={stirBarRef}
        data-part="stir-bar"
        x={bioreactor.stirBar.x - 5} y={bioreactor.stirBar.y}
        width={bioreactor.stirBar.maxWidth + 10} height={bioreactor.stirBar.height}
        rx={bioreactor.stirBar.radius}
      />
      {ledRects.map(led => (
        <g key={led.label} data-led={led.label}>
          {/* Keep intensity's translucent amber over a light base in both modes. */}
          {leds[led.label] > 0 && (
            <rect x={led.x} y={led.y} width={40} height={30} rx={3} fill="#fff" stroke="none" />
          )}
          <rect
            x={led.x} y={led.y} width={40} height={30} rx={3}
            fill={leds[led.label] > 0 ? `rgba(234, 188, 116, ${leds[led.label] / 100 + 0.2})` : 'var(--diagram-surface)'}
          />
          <text x={led.x + 20} y={led.y + 15} fill={leds[led.label] > 0 ? "#000" : "var(--diagram-ink)"} stroke="none">{led.label}</text>
        </g>
      ))}
      {tubes.map(tube => (
        <g key={tube.id} data-tube={tube.id} strokeWidth={tube.active ? 4 : 3}>
          <rect
            x={tube.x} y={tube.y} width={tube.width} height={tube.tipY - tube.y}
            rx={tube.radius} fill={tube.active ? '#EABC74' : 'var(--diagram-surface)'}
          />
          <text
            transform={`translate(${tube.x + tube.width / 2} ${tube.y + (tube.tipY - tube.y) / 2}) rotate(-90)`}
            fill={tube.active ? "#000" : "var(--diagram-ink)"} stroke="none"
          >
            {tube.label}
          </text>
          {tube.airStone && (
            <rect
              x={tube.airStone.x} y={tube.airStone.y} width={tube.airStone.width}
              height={tube.airStone.height} rx={tube.airStone.radius}
              fill={tube.active ? '#EABC74' : '#99999B'}
            />
          )}
        </g>
      ))}
      {dynamicRects.map(label => (
        <g key={label.x}>
          <rect x={label.x} y={260 + diagramYOffset} width={label.width} height={30} rx={3} />
          <text x={label.x + label.width / 2} y={275 + diagramYOffset} fill="var(--diagram-ink)" stroke="none">
            {label.text}
          </text>
        </g>
      ))}
      {volume !== 0 && (
        <g stroke="var(--diagram-muted)" strokeWidth={1}>
          <text x={bioreactor.x + 100} y={volumeLabelY} fill="var(--diagram-muted)" stroke="none">
            {roundTo1(volume)} mL
          </text>
          <line
            x1={bioreactor.x + 100} x2={bioreactor.x + 100}
            y1={volumeLabelY + 9} y2={liquidSurfaceY} strokeDasharray="2 3"
          />
        </g>
      )}
      <g data-part="heater">
        <rect x={100} y={shiftedBaseHigh - 10} width={200} height={20} rx={3} fill={heat ? '#D8A0A2' : 'var(--diagram-surface)'} />
        <text x={200} y={shiftedBaseHigh} fill={heat ? "#000" : "var(--diagram-ink)"} stroke="none">heat</text>
      </g>
      {liquidPumpActive && (
        <g fill="rgb(255, 244, 229)" stroke="rgb(102, 60, 0)">
          <rect x={40} y={450} width={320} height={50} rx={3} />
          <text x={200} y={450 + 50 / 3} fontSize={14} fill="rgb(102, 60, 0)" stroke="none">
            <tspan x={200}>⚠ diagram above may not be an accurate</tspan>
            <tspan x={200} dy="1em">representation of the volume. Observe carefully.</tspan>
          </text>
        </g>
      )}
    </Box>
  );
};

export default BioreactorDiagram;
