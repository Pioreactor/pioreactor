import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { useMQTT } from '../providers/MQTTContext';

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

const PIN_TO_PWM = {
  17: 1,
  13: 2,
  16: 3,
  12: 4,
  18: 5, // heater
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
  const [rpm, setRpm] = useState(null);
  const [temperature, setTemperature] = useState(null);
  const [nOD, setNOD] = useState(null);
  const [leds, setLeds] = useState({ A: 0, B: 0, C: 0, D: 0 });
  const [pumps, setPumps] = useState(new Set());
  const [heat, setHeat] = useState(false);

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

  const fps = 45;
  const fpsInterval = 1000 / fps;

  const onMessage = useCallback((topic, message) => {
    if (!message || !topic) return;

    const topicString = topic.toString();
    const messageString = message.toString();

    if (topicString.endsWith('pwms/dc')) {
      const pumps_ = new Set();
      let rpm_ = null;
      let heat_ = false;

      if (messageString === '') {
        setPumps(pumps_);
        setRpm(rpm_);
        setHeat(heat_);
        return;
      }

      const dcs = JSON.parse(messageString);
      for (const pin of Object.keys(dcs)) {
        const pwmOutput = PIN_TO_PWM[pin];
        const load = config.PWM[pwmOutput];
        switch (load) {
          case 'stirring':
            const rpmEstimate = parseFloat(dcs[pin]) * 26.66666667;
            rpm_ = Math.min(Math.max(rpmEstimate, 100), rpmClampMax);
            break;
          case 'media':
            pumps_.add('media');
            break;
          case 'alt_media':
            pumps_.add('alt-media');
            break;
          case 'waste':
            pumps_.add('efflux');
            break;
          case 'heating':
            heat_ = true;
            break;
          default:
        }
      }
      setPumps(pumps_);
      setRpm(rpm_);
      setHeat(heat_);

    } else if (topicString.endsWith('temperature_automation/temperature')) {
      setTemperature(messageString ? JSON.parse(messageString).temperature : null);
    } else if (topicString.endsWith('growth_rate_calculating/od_filtered')) {
      setNOD(messageString ? JSON.parse(messageString).od_filtered : null);
    } else if (topicString.endsWith('leds/intensity')) {
      setLeds(messageString ? JSON.parse(messageString) : { A: 0, B: 0, C: 0, D: 0 });
    }
  }, [config, rpmClampMax]);

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
    let now;
    let elapsed;
    const liquidLevel = (volume / size) * bioreactor.height;
    const bottomOfWasteTube = bioreactor.height - (cappedMaxVolume / size) * bioreactor.height + 53; // bioreactor.height - maxVolume / 40 * bioreactor.height + 20

    const ledsRects = [];
    const ledY = shiftedBaseLow - 20;
    ledsRects.push({ text: 'B', x: 50, y: ledY + 50, width: 40, height: 30, radius: 3 });
    ledsRects.push({ text: 'D', x: 310, y: ledY + 50, width: 40, height: 30, radius: 3 });
    ledsRects.push({ text: 'A', x: 50, y: ledY, width: 40, height: 30, radius: 3 });
    ledsRects.push({ text: 'C', x: 310, y: ledY, width: 40, height: 30, radius: 3 });

    const heaterRec = [{ text: 'heat', x: 100, y: shiftedBaseHigh - 10, width: 200, height: 20, radius: 3 }];

    const pumpsRects = [
      { text: 'efflux', x: bioreactor.x + (bioreactor.width * 3) / 4, y: bioreactor.y - 53, width: 20, height: bottomOfWasteTube, radius: 3 },
      { text: 'media', x: bioreactor.x + (bioreactor.width * 2) / 4, y: bioreactor.y - 53, width: 20, height: 100, radius: 3 },
      { text: 'alt-media', x: bioreactor.x + bioreactor.width / 4, y: bioreactor.y - 53, width: 20, height: 100, radius: 3 },
    ];

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
    if (volume) {
      dynamicRects.push({ text: `${roundTo1(volume)} mL`, x: 110, y: Math.max(bioreactor.y + bioreactor.height - liquidLevel - 35, 40), width: 90, height: 30, radius: 3 });
    }

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
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, '#fff', '#000');
        ctx.stroke();
        ctx.fillStyle = '#000';
        if (label.text.length > 60) {
          fillTextMultiLine(ctx, label.text, label.x + label.width / 2, label.y + label.height / 3);
        } else {
          ctx.fillText(label.text, label.x + label.width / 2, label.y + label.height / 2);
        }
      });
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

    function drawLabeledPumps(pumpsArray) {
      ctx.lineWidth = 3;
      ctx.font = "13px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      pumpsArray.forEach(label => {
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, pumps.has(label.text) ? '#EABC74' : '#fff', '#000');
        ctx.stroke();
        ctx.save();
        ctx.translate(label.x + label.width / 2, label.y + label.height / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillStyle = '#000';
        ctx.fillText(label.text, 0, 0);
        ctx.restore();
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
        Math.max(bioreactor.y + bioreactor.height - liquidLevel, bioreactor.y),
        bioreactor.width,
        Math.min(liquidLevel, bioreactor.height),
        nOD
      );

      // dashed bottom of waste tube
      ctx.beginPath();
      ctx.setLineDash([4, 3]);
      ctx.strokeStyle = 'grey';
      ctx.lineWidth = 1;
      ctx.moveTo(bioreactor.x + 2, bioreactor.y + bottomOfWasteTube - 53);
      ctx.lineTo(bioreactor.x + bioreactor.width - 2, bioreactor.y + bottomOfWasteTube - 53);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'grey';
      ctx.font = "12px 'Roboto'";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText(
        `${roundTo1(cappedMaxVolume)} mL`,
        bioreactor.x + bioreactor.width / 2 + 60,
        bioreactor.y + bottomOfWasteTube - 30
      );
      ctx.restore();

      drawRoundedRect(cap.x, cap.y, cap.width, cap.height, cap.radius, '#ececed', '#E0E0E1', 6);
      ctx.lineWidth = 6;
      ctx.strokeStyle = '#000';
      ctx.beginPath();
      ctx.stroke();
      const angle = (2 * Math.PI / (frameFactor * fps / rpm)) * stirBarFrame.current;
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
      drawLabeledPumps(pumpsRects);
      drawLabeledRectangles(dynamicRects);
      drawLabeledHeat(heaterRec);
      if (pumps.size) drawWarning(warningRects);
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
  }, [bioreactor, canvasDim, cap, cappedMaxVolume, fpsInterval, frameFactor, heat, leds, nOD, pumps, rpm, shiftedBaseHigh, shiftedBaseLow, size, temperature, volume]);

  return (
    <div>
      <canvas
        style={{ display: 'block', margin: '0 auto' }}
        ref={canvasRef}
        width={canvasDim.width}
        height={canvasDim.height}
      />
    </div>
  );
};

export default BioreactorDiagram;
