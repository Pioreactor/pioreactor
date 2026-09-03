import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import Box from '@mui/material/Box';
import { useMQTT } from '../providers/MQTTContext';
import { getBioreactorTubeLayout, getPwmDutyCyclesByLoad } from './bioreactorDiagramModel';

function roundTo1(x) {
  return `${Math.round(x * 10) / 10}`;
}

function binFloat(value, binSize) {
  return Math.floor(value / binSize) * binSize;
}

const versionMap = {
  20: {
    canvasDim: { width: 400, height: 510 },
    bioreactorHeight: 400,
    stirBarOffset: 160,
    frameFactor: 200,
    rpmClampMax: 600,
    baseLow: 320,
    baseHigh: 455,
  },
  40: {
    canvasDim: { width: 400, height: 610 },
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

const BioreactorDiagram = ({ experiment, unit, config, size, liquidVolume, maxVolume, hasAirBubbler = false }) => {
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();

  const {
    canvasDim,
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
    x: (canvasDim.width - 200) / 2,
    y: (canvasDim.height - bioreactorHeight) / 2 - 20 + diagramYOffset,
    cornerRadius: 20,
    stirBar: {
      maxWidth: 70,
      height: 10,
      x: (canvasDim.width - 70) / 2,
      y: (canvasDim.height - 10) / 2 + stirBarOffset + diagramYOffset,
      radius: 3,
    },
  }), [bioreactorHeight, canvasDim.height, canvasDim.width, diagramYOffset, stirBarOffset]);
  const cap = useMemo(() => ({
    width: bioreactor.width * 0.95,
    height: 52,
    x: bioreactor.x + 5,
    y: bioreactor.y - 63,
    radius: 3,
  }), [bioreactor.width, bioreactor.x, bioreactor.y]);

  const canvasRef = useRef(null);
  const stirBarFrame = useRef(0);
  const [dutyCyclesByPin, setDutyCyclesByPin] = useState({});
  const [temperature, setTemperature] = useState(null);
  const [nOD, setNOD] = useState(null);
  const [leds, setLeds] = useState({ A: 0, B: 0, C: 0, D: 0 });
  const dutyCyclesByLoad = useMemo(
    () => getPwmDutyCyclesByLoad(dutyCyclesByPin, config?.PWM),
    [dutyCyclesByPin, config],
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
      hasAirBubbler,
    });
    return {
      ...layout,
      tubes: layout.tubes.map(tube => ({ ...tube, active: dutyCyclesByLoad[tube.load] > 0 })),
    };
  }, [bioreactor, size, volume, cappedMaxVolume, dutyCyclesByLoad, hasAirBubbler]);

  const fps = 45;
  const fpsInterval = 1000 / fps;

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

  useEffect(() => {
    let animationFrameId;
    const canvas = canvasRef.current;
    if (!canvas) {
      return undefined;
    }
    const ctx = canvas.getContext('2d');
    const isAnimating = Number.isFinite(rpm) && rpm > 0;
    let now;
    let elapsed;

    const ledsRects = [];
    const ledY = shiftedBaseLow - 20;
    ledsRects.push({ text: 'B', x: 50, y: ledY + 50, width: 40, height: 30, radius: 3 });
    ledsRects.push({ text: 'D', x: 310, y: ledY + 50, width: 40, height: 30, radius: 3 });
    ledsRects.push({ text: 'A', x: 50, y: ledY, width: 40, height: 30, radius: 3 });
    ledsRects.push({ text: 'C', x: 310, y: ledY, width: 40, height: 30, radius: 3 });

    const heaterRec = [{ text: 'heat', x: 100, y: shiftedBaseHigh - 10, width: 200, height: 20, radius: 3 }];

    const warningRects = [
      { text: '⚠ diagram above may not be an accurate\nrepresentation of the volume. Observe carefully.', x: 40, y: 450, width: 320, height: 50, radius: 3 },
    ];

    const dynamicRects = [];
    if (temperature) {
      dynamicRects.push({ text: `Temp: ${roundTo1(temperature)}°C`, x: 110, y: 260 + diagramYOffset, width: 90, height: 30, radius: 3 });
    }
    if (nOD) {
      dynamicRects.push({ text: `nOD: ${roundTo1(nOD)}`, x: 210, y: 260 + diagramYOffset, width: 80, height: 30, radius: 3 });
    }
    const volumeLabel = volume
      ? {
          text: `${roundTo1(volume)} mL`,
          x: bioreactor.x + 100,
          y: Math.max(liquidSurfaceY - 30, 40),
        }
      : null;

    function drawRoundedRect(x, y, width, height, radius, fillStyle, strokeStyle, lineWidth = 3) {
      ctx.lineWidth = lineWidth;
      ctx.beginPath();
      ctx.moveTo(x + radius, y);
      ctx.lineTo(x + width - radius, y);
      ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
      ctx.lineTo(x + width, y + height - radius);
      ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
      ctx.lineTo(x + radius, y + height);
      ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
      ctx.lineTo(x, y + radius);
      ctx.quadraticCurveTo(x, y, x + radius, y);
      ctx.closePath();
      ctx.fillStyle = fillStyle;
      ctx.fill();
      ctx.strokeStyle = strokeStyle;
      ctx.stroke();
    }

    function pseudoRandom(x, y) {
      return Math.abs(Math.sin(x * 976.34 + y)) % 1;
    }

    function drawTurbidLiquid(x, y, width, height, turbidity) {
      if (height <= 0) return;
      drawRoundedRect(x, y, width, height, 10, '#e0d0b5', '#000');
      if (!turbidity) return;
      ctx.strokeStyle = '#e0d0b540';
      ctx.lineWidth = 1;
      const waveHeight = 5;
      const waveSpacing = 150 / binFloat(turbidity, 0.1);
      for (let i = y + 10; i < y + height; i += waveSpacing) {
        ctx.beginPath();
        const r = pseudoRandom(pseudoRandom(i, 0.618), pseudoRandom(i, 1.618));
        for (let j = x; j <= x + width; j += 10) {
          ctx.lineTo(j, i + Math.sin((1 + r) * (j / 10)) * waveHeight);
        }
        ctx.stroke();
      }
    }

    function drawOutline() {
      ctx.lineWidth = 8;
      ctx.beginPath();
      const start = (canvasDim.height - bioreactor.height) / 2 + diagramYOffset;
      ctx.moveTo(70, start - 50);
      ctx.lineTo(70, shiftedBaseLow - 50);
      ctx.lineTo(20, shiftedBaseLow - 50);
      ctx.lineTo(20, shiftedBaseHigh - 50);
      ctx.lineTo(55, shiftedBaseHigh - 50);
      ctx.lineTo(55, canvasDim.height - 30 + diagramYOffset);
      ctx.lineTo(canvasDim.width - 55, canvasDim.height - 30 + diagramYOffset);
      ctx.lineTo(canvasDim.width - 55, shiftedBaseHigh - 50);
      ctx.lineTo(canvasDim.width - 20, shiftedBaseHigh - 50);
      ctx.lineTo(canvasDim.width - 20, shiftedBaseLow - 50);
      ctx.lineTo(canvasDim.width - 70, shiftedBaseLow - 50);
      ctx.lineTo(canvasDim.width - 70, start - 50);
      ctx.closePath();
      ctx.fillStyle = 'rgba(0,0,0,0.01)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(0,0,0,0.04)';
      ctx.stroke();
    }

    function fillTextMultiLine(ctx, text, x, y) {
      const lineHeight = ctx.measureText('M').width * 1.2;
      const lines = text.split('\n');
      lines.forEach(line => {
        ctx.fillText(line, x, y);
        y += lineHeight;
      });
    }

    function drawLabeledRectangles(labelsArray) {
      ctx.lineWidth = 3;
      ctx.font = "13px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      labelsArray.forEach(label => {
        ctx.save();
        ctx.setLineDash(label.lineDash || []);
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, '#fff', label.strokeStyle || '#000', label.lineWidth);
        ctx.stroke();
        ctx.fillStyle = label.textStyle || '#000';
        if (label.text.length > 60) {
          fillTextMultiLine(ctx, label.text, label.x + label.width / 2, label.y + label.height / 3);
        } else {
          ctx.fillText(label.text, label.x + label.width / 2, label.y + label.height / 2);
        }
        ctx.restore();
      });
    }

    function drawVolumeLabel(label) {
      ctx.save();
      ctx.font = "13px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'grey';
      ctx.fillText(label.text, label.x, label.y);

      ctx.beginPath();
      ctx.setLineDash([2, 3]);
      ctx.strokeStyle = 'grey';
      ctx.lineWidth = 1;
      ctx.moveTo(label.x, label.y + 9);
      ctx.lineTo(label.x, liquidSurfaceY);
      ctx.stroke();
      ctx.restore();
    }

    function drawWarning(labelsArray) {
      ctx.lineWidth = 3;
      ctx.font = "14px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      labelsArray.forEach(label => {
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, 'rgb(255, 244, 229)', 'rgb(102, 60, 0)');
        ctx.stroke();
        ctx.fillStyle = 'rgb(102, 60, 0)';
        if (label.text.length > 60) {
          fillTextMultiLine(ctx, label.text, label.x + label.width / 2, label.y + label.height / 3);
        } else {
          ctx.fillText(label.text, label.x + label.width / 2, label.y + label.height / 2);
        }
      });
    }

    function drawLabeledHeat(labelsArray) {
      ctx.lineWidth = 3;
      ctx.font = "13px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      labelsArray.forEach(label => {
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, heat ? '#D8A0A2' : '#fff', '#000');
        ctx.stroke();
        ctx.fillStyle = '#000';
        ctx.fillText(label.text, label.x + label.width / 2, label.y + label.height / 2);
      });
    }

    function drawTubes(tubesArray) {
      ctx.lineWidth = 3;
      ctx.font = "13px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      tubesArray.forEach(tube => {
        const height = tube.tipY - tube.y;
        const activeLineWidth = tube.load === 'air_bubbler' && tube.active ? 5 : 3;
        drawRoundedRect(tube.x, tube.y, tube.width, height, tube.radius, tube.active ? '#EABC74' : '#fff', '#000', activeLineWidth);
        ctx.stroke();
        ctx.save();
        ctx.translate(tube.x + tube.width / 2, tube.y + height / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillStyle = '#000';
        ctx.fillText(tube.label, 0, 0);
        ctx.restore();

        if (tube.airStone) {
          drawRoundedRect(
            tube.airStone.x,
            tube.airStone.y,
            tube.airStone.width,
            tube.airStone.height,
            tube.airStone.radius,
            tube.active ? '#EABC74' : '#99999B',
            '#000',
            activeLineWidth,
          );
        }
      });
    }

    function drawLabeledLeds(ledsRects) {
      ctx.lineWidth = 3;
      ctx.font = "13px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ledsRects.forEach(label => {
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, leds[label.text] > 0 ? `rgba(234, 188, 116, ${leds[label.text] / 100 + 0.2})` : '#fff', '#000');
        ctx.stroke();
        ctx.fillStyle = '#000';
        ctx.fillText(label.text, label.x + label.width / 2, label.y + label.height / 2);
      });
    }

    function drawBioreactor() {
      ctx.clearRect(0, 0, canvasDim.width, canvasDim.height);
      drawOutline();
      drawRoundedRect(bioreactor.x, bioreactor.y, bioreactor.width, bioreactor.height, bioreactor.cornerRadius, 'rgb(244,244,244)', '#000');
      ctx.save();
      drawTurbidLiquid(
        bioreactor.x,
        Math.max(liquidSurfaceY, bioreactor.y),
        bioreactor.width,
        Math.min(liquidHeight, bioreactor.height),
        nOD
      );

      // dashed bottom of waste tube
      ctx.beginPath();
      ctx.setLineDash([4, 3]);
      ctx.strokeStyle = 'grey';
      ctx.lineWidth = 1;
      ctx.moveTo(bioreactor.x + 2, wasteTubeTipY);
      ctx.lineTo(bioreactor.x + bioreactor.width - 2, wasteTubeTipY);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'grey';
      ctx.font = "12px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText(
        `${roundTo1(cappedMaxVolume)} mL`,
        bioreactor.x + bioreactor.width / 2 + 60,
        wasteTubeTipY + 23
      );
      ctx.restore();

      drawRoundedRect(cap.x, cap.y, cap.width, cap.height, cap.radius, '#ececed', '#E0E0E1', 6);
      ctx.lineWidth = 6;
      ctx.strokeStyle = '#000';
      ctx.beginPath();
      ctx.stroke();
      const angle = isAnimating
        ? (2 * Math.PI / (frameFactor * fps / rpm)) * stirBarFrame.current
        : 0;
      const width = bioreactor.stirBar.maxWidth * Math.abs(Math.cos(angle)) + 10;
      drawRoundedRect(
        bioreactor.stirBar.x + (bioreactor.stirBar.maxWidth - width) / 2,
        bioreactor.stirBar.y,
        width,
        bioreactor.stirBar.height,
        bioreactor.stirBar.radius,
        '#fff',
        '#000'
      );
      drawLabeledLeds(ledsRects);
      drawTubes(tubes);
      drawLabeledRectangles(dynamicRects);
      if (volumeLabel) drawVolumeLabel(volumeLabel);
      drawLabeledHeat(heaterRec);
      if (liquidPumpActive) drawWarning(warningRects);
    }

    if (!isAnimating) {
      drawBioreactor();
      return undefined;
    }

    function startAnimating() {
      let then = window.performance.now();

      function update() {
        animationFrameId = window.requestAnimationFrame(update);
        now = window.performance.now();
        elapsed = now - then;
        if (elapsed > fpsInterval) {
          then = now - (elapsed % fpsInterval);
          stirBarFrame.current = (stirBarFrame.current + 1) % Math.round(frameFactor * fps / rpm);
          drawBioreactor();
        }
      }

      update();
    }
    startAnimating();
    return () => window.cancelAnimationFrame(animationFrameId);
  }, [bioreactor, canvasDim, cap, cappedMaxVolume, fpsInterval, frameFactor, heat, leds, liquidHeight, liquidPumpActive, liquidSurfaceY, nOD, rpm, shiftedBaseHigh, shiftedBaseLow, temperature, tubes, volume, wasteTubeTipY]);

  return (
    <div>
      <Box
        component="canvas"
        role="img"
        aria-label={`Bioreactor diagram${hasAirBubbler ? `. Air bubbler is ${dutyCyclesByLoad.air_bubbler > 0 ? 'on' : 'off'}.` : '.'}`}
        sx={{ display: 'block', m: '0 auto' }}
        ref={canvasRef}
        width={canvasDim.width}
        height={canvasDim.height}
      />
    </div>
  );
};

export default BioreactorDiagram;
