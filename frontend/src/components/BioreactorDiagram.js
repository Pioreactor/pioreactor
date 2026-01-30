import React, { useRef, useEffect, useState } from 'react';
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

const BioreactorDiagram = ({ experiment, unit, config, size }) => {
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

  const bioreactor = {
    width: 200,
    height: bioreactorHeight,
    x: (canvasDim.width - 200) / 2,
    y: (canvasDim.height - bioreactorHeight) / 2 - 20,
    cornerRadius: 10,
    stirBar: {
      maxWidth: 70,
      height: 10,
      x: (canvasDim.width - 70) / 2,
      y: (canvasDim.height - 10) / 2 + stirBarOffset,
      radius: 5,
    },
  };

  const canvasRef = useRef(null);
  const stirBarFrame = useRef(0);
  const [rpm, setRpm] = useState(null);
  const [temperature, setTemperature] = useState(null);
  const [nOD, setNOD] = useState(null);
  const [leds, setLeds] = useState({ A: 0, B: 0, C: 0, D: 0 });
  const [pumps, setPumps] = useState(new Set());
  const [heat, setHeat] = useState(false);
  const [volume, setVolume] = useState(size === 20 ? 14 : 20);
  const [maxVolume, setMaxVolume] = useState(
     Math.min(size, config?.bioreactor?.max_working_volume_ml || size)
  );

  let now, then, elapsed;
  const fps = 45;
  const fpsInterval = 1000 / fps;

  useEffect(() => {
    if (Object.keys(config || {}).length) {
      setVolume(
        Math.min(config?.bioreactor?.initial_volume_ml, size)
      );
    }
  }, [config, size]);

  function onMessage(topic, message) {
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
            pumps_.add('waste');
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
    } else if (topicString.endsWith('dosing_automation/current_volume_ml')) {
      if (messageString) {
        const v = parseFloat(messageString);
        setVolume(Math.min(v, size));
      }
    } else if (topicString.endsWith('dosing_automation/max_working_volume_ml')) {
      if (messageString) {
        const m = parseFloat(messageString);
        setMaxVolume(Math.min(m, size));
      }
    } else if (topicString.endsWith('leds/intensity')) {
      setLeds(messageString ? JSON.parse(messageString) : { A: 0, B: 0, C: 0, D: 0 });
    }
  }

  useEffect(() => {
    if (!client || !experiment || !config || Object.keys(config).length === 0) {
      return undefined;
    }
    const topics = [
      `pioreactor/${unit}/${experiment}/temperature_automation/temperature`,
      `pioreactor/${unit}/${experiment}/growth_rate_calculating/od_filtered`,
      `pioreactor/${unit}/${experiment}/leds/intensity`,
      `pioreactor/${unit}/${experiment}/dosing_automation/current_volume_ml`,
      `pioreactor/${unit}/${experiment}/dosing_automation/max_working_volume_ml`,
      `pioreactor/${unit}/${experiment}/pwms/dc`,
      `pioreactor/${unit}/_testing_${experiment}/temperature_automation/temperature`,
      `pioreactor/${unit}/_testing_${experiment}/growth_rate_calculating/od_filtered`,
      `pioreactor/${unit}/_testing_${experiment}/leds/intensity`,
      `pioreactor/${unit}/_testing_${experiment}/dosing_automation/current_volume_ml`,
      `pioreactor/${unit}/_testing_${experiment}/dosing_automation/max_working_volume_ml`,
      `pioreactor/${unit}/_testing_${experiment}/pwms/dc`,
    ];
    subscribeToTopic(topics, onMessage, 'BioreactorDiagram');
    return () => {
      unsubscribeFromTopic(topics, 'BioreactorDiagram');
    };
  }, [client, experiment, config, size, subscribeToTopic, unsubscribeFromTopic, unit]);

  useEffect(() => {
    let animationFrameId;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const liquidLevel = (volume / size) * bioreactor.height;
    const bottomOfWasteTube = bioreactor.height - (maxVolume / size) * bioreactor.height + 20; // bioreactor.height - maxVolume / 40 * bioreactor.height + 20

    const ledsRects = [];
    const ledY = baseLow - 20;
    ledsRects.push({ text: 'B', x: 50, y: ledY + 50, width: 40, height: 30, radius: 5 });
    ledsRects.push({ text: 'D', x: 310, y: ledY + 50, width: 40, height: 30, radius: 5 });
    ledsRects.push({ text: 'A', x: 50, y: ledY, width: 40, height: 30, radius: 5 });
    ledsRects.push({ text: 'C', x: 310, y: ledY, width: 40, height: 30, radius: 5 });

    const heaterRec = [{ text: 'heat', x: 100, y: baseHigh - 10, width: 200, height: 20, radius: 3 }];

    const pumpsRects = [
      { text: 'waste', x: bioreactor.x + (bioreactor.width * 3) / 4, y: bioreactor.y - 20, width: 20, height: bottomOfWasteTube, radius: 3 },
      { text: 'media', x: bioreactor.x + (bioreactor.width * 2) / 4, y: bioreactor.y - 20, width: 20, height: 100, radius: 3 },
      { text: 'alt-media', x: bioreactor.x + bioreactor.width / 4, y: bioreactor.y - 20, width: 20, height: 100, radius: 3 },
    ];

    const warningRects = [
      { text: '⚠ diagram above may not be an accurate\nrepresentation of the volume. Observe carefully.', x: 40, y: 450, width: 320, height: 50, radius: 5 },
    ];

    const dynamicRects = [];
    if (temperature) {
      dynamicRects.push({ text: `Temp: ${roundTo1(temperature)}°C`, x: 110, y: 260, width: 90, height: 30, radius: 5 });
    }
    if (nOD) {
      dynamicRects.push({ text: `nOD: ${roundTo1(nOD)}`, x: 210, y: 260, width: 80, height: 30, radius: 5 });
    }
    if (volume) {
      dynamicRects.push({ text: `${roundTo1(volume)} mL`, x: 110, y: Math.max(bioreactor.y + bioreactor.height - liquidLevel - 35, 40), width: 90, height: 30, radius: 5 });
    }

    function drawRoundedRect(x, y, width, height, radius, fillStyle, strokeStyle) {
      ctx.lineWidth = 2;
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

    function drawTurbidLiquid(x, y, width, height, radius, turbidity) {
      if (height <= 0) return;
      if (height > 30) {
        drawRoundedRect(x, y, width, height, radius, '#E1DDFF', '#000');
      } else {
        drawRoundedRect(x, y, width, height, 10, '#E1DDFF', '#000');
      }
      if (!turbidity) return;
      ctx.strokeStyle = '#4D3AC340';
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
      const start = (canvasDim.height - bioreactor.height) / 2;
      ctx.moveTo(70, start - 50);
      ctx.lineTo(70, baseLow - 50);
      ctx.lineTo(20, baseLow - 50);
      ctx.lineTo(20, baseHigh - 50);
      ctx.lineTo(55, baseHigh - 50);
      ctx.lineTo(55, canvasDim.height - 30);
      ctx.lineTo(canvasDim.width - 55, canvasDim.height - 30);
      ctx.lineTo(canvasDim.width - 55, baseHigh - 50);
      ctx.lineTo(canvasDim.width - 20, baseHigh - 50);
      ctx.lineTo(canvasDim.width - 20, baseLow - 50);
      ctx.lineTo(canvasDim.width - 70, baseLow - 50);
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
      ctx.lineWidth = 2;
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
      ctx.lineWidth = 2;
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
      ctx.lineWidth = 2;
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
      ctx.lineWidth = 2;
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
      ctx.lineWidth = 2;
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
      drawTurbidLiquid(
        bioreactor.x,
        Math.max(bioreactor.y + bioreactor.height - liquidLevel, bioreactor.y),
        bioreactor.width,
        Math.min(liquidLevel, bioreactor.height),
        bioreactor.cornerRadius,
        nOD
      );
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

    function startAnimating() {
      then = window.performance.now();
      update();
    }
    startAnimating();
    return () => window.cancelAnimationFrame(animationFrameId);
  }, [rpm, temperature, nOD, leds, pumps, volume, heat, size]);

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
