import React, { useRef, useEffect, useState } from 'react';
import { useMQTT } from '../providers/MQTTContext';


function roundTo1(x){
  return `${Math.round(x * 10) / 10}`
}

function binFloat(value, binSize) {
    return Math.floor(value / binSize) * binSize;
}

const canvasDim = {
  height: 610,
  width: 400
}

const bioreactor = {
  width: 200,
  height: 500,
  x: (canvasDim.width - 200) / 2,
  y: (canvasDim.height - 500) / 2 - 20,
  cornerRadius: 10,
  stirBar: {
    maxWidth: 70,
    height: 10,
    x: (canvasDim.width - 70) / 2,
    y: (canvasDim.height - 10) / 2 + 210,
    radius: 5
  },
};

const PIN_TO_PWM = {
  17: 1,
  13: 2,
  16: 3,
  12: 4,
  18: 5 //heater
}


const Bioreactor40Diagram = ({experiment, unit, config}) => {
  const {client, subscribeToTopic } = useMQTT();

  const canvasRef = useRef(null);
  const stirBarFrame = useRef(0)
  const [rpm, setRpm] = useState(null);
  const [temperature, setTemperature] = useState(null);
  const [nOD, setNOD] = useState(null);
  const [leds, setLeds] = useState({A: 0, B: 0, C: 0, D: 0});
  const [pumps, setPumps] = useState(new Set([]));
  const [heat, setHeat] = useState(false);
  const [volume, setVolume] = useState(20);
  const [maxVolume, setMaxVolume] = useState((config?.bioreactor?.max_working_volume_ml || 14));
  var  now, then, elapsed;
  const fps = 45;
  const fpsInterval = 1000 / fps;


  useEffect(() => {
    if (Object.keys(config).length){
      setVolume(config?.bioreactor?.initial_volume_ml)
    }
  }, [config])



  function onMessage(topic, message) {
    if (!message || !topic) return;

    const topicString = topic.toString()
    const messageString = message.toString()


    if (topicString.endsWith("pwms/dc")) {
      // reset these, unless otherwise set later.
      var pumps_ = new Set([])
      var rpm_ = null
      var heat_ = false

      if (messageString === ""){
        setPumps(pumps_)
        setRpm(rpm_)
        setHeat(heat_)
        return
      }

      const dcs = JSON.parse(messageString) // {17: 10.3, 12: 34.3}

      for (const pin of  Object.keys(dcs)) {
        const pwmOutput = PIN_TO_PWM[pin]
        // now what load is that:
        const load = config.PWM[pwmOutput]

        switch (load){
          case "stirring":
            const rpm_estimate = parseFloat(dcs[pin]) * 26.66666667
            rpm_ = Math.min(Math.max(rpm_estimate, 100), 800)
            break
          case "media":
            pumps_.add('media')
            break
          case "alt_media":
            pumps_.add('alt-media')
            break
          case "waste":
            pumps_.add('waste')
            break
          case "heating":
            heat_ = true
            break
          default:
            break
        }
      }
      setPumps(pumps_)
      setRpm(rpm_)
      setHeat(heat_)

    } else if (topicString.endsWith("temperature_automation/temperature")){
      if (messageString === "") {
        setTemperature(null)
      } else {
        setTemperature(JSON.parse(messageString).temperature)
      }
    } else if (topicString.endsWith("growth_rate_calculating/od_filtered")){
      if (messageString === "") {
        setNOD(null)
      } else {
        setNOD(JSON.parse(messageString).od_filtered)
      }
    } else if (topicString.endsWith("dosing_automation/current_volume_ml")){
      if (messageString === "") {
        //
      } else {
        setVolume(parseFloat(messageString))
      }
    } else if (topicString.endsWith("dosing_automation/max_working_volume_ml")){
      if (messageString === "") {
        //
      } else {
        setMaxVolume(parseFloat(messageString))
      }
    } else if (topicString.endsWith("leds/intensity")){
      if (messageString === "") {
        setLeds({A: 0, B: 0, C: 0, D: 0})
      } else {
        setLeds(JSON.parse(messageString))
      }
    }
  }

  useEffect(() => {
    if (client && experiment && config && Object.keys(config).length > 0){
      subscribeToTopic([`pioreactor/${unit}/${experiment}/temperature_automation/temperature`,
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
      ], onMessage, "BioreactorDiagram")

    }
  }, [client, experiment, config])

  useEffect(() => {
    let animationFrameId;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const liquidLevel = volume / 40 * bioreactor.height
    const bottomOfWasteTube = bioreactor.height - maxVolume / 40 * bioreactor.height + 20

    const ledsRects = [
      { text: 'B', x: 50,  y: 450, width: 40, height: 30, radius: 5 },
      { text: 'D', x: 310, y: 450, width: 40, height: 30, radius: 5 },
      { text: 'A', x: 50,  y: 400, width: 40, height: 30, radius: 5 },
      { text: 'C', x: 310, y: 400, width: 40, height: 30, radius: 5 },
    ]

    const heaterRec = [
      { text: 'heat', x: 100,  y: 550, width: 200, height: 20, radius: 3 },
    ]

    const pumpsRects = [
      { text: 'waste', x: bioreactor.x + bioreactor.width * 3 / 4, y: bioreactor.y - 20, width: 20, height: bottomOfWasteTube, radius: 3 },
      { text: 'media', x: bioreactor.x + bioreactor.width * 2 / 4, y: bioreactor.y - 20, width: 20, height: 100, radius: 3 },
      { text: 'alt-media', x: bioreactor.x + bioreactor.width * 1 / 4, y: bioreactor.y - 20, width: 20, height: 100, radius: 3 },
    ];

    const warningRects = [
      { text: '⚠ diagram above may not be an accurate\nrepresentation of the volume. Observe carefully.', x: 40, y: 450, width: 320, height: 50, radius: 5 },
    ]

    var dynamicRects = []
    if (temperature){
      dynamicRects.push({ text: `Temp: ${roundTo1(temperature)}°C`, x: 110, y: 260, width: 90, height: 30, radius: 5 })
    }
    if (nOD){
      dynamicRects.push({ text: `nOD: ${roundTo1(nOD)}`, x: 210, y: 260, width: 80, height: 30, radius: 5 })
    }
    if (volume){
      dynamicRects.push({ text: `${roundTo1(volume)} mL`, x: 110, y: Math.max(bioreactor.y + bioreactor.height - liquidLevel - 35, 40), width: 90, height: 30, radius: 5 })
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
      if (height <= 0){
        return
      }

      // Draw the liquid with rounded corners
      if (height > 30){
        drawRoundedRect(x, y, width, height, radius, '#E1DDFF', '#000');
      } else {
        drawRoundedRect(x, y, width, height, 10, '#E1DDFF', '#000');
      }

      if (!turbidity){
        return
      }

      // Draw wavy lines to simulate turbidity
      ctx.strokeStyle = '#4D3AC340';
      ctx.lineWidth = 1;
      const waveHeight = 5;
      const waveSpacing = 150 / binFloat(turbidity, 0.1);
      for (let i = y + 10; i < y + height; i += waveSpacing) {
        ctx.beginPath();
        const r = pseudoRandom(pseudoRandom(i, 0.618), pseudoRandom(i, 1.618))
        for (let j = x; j <= x + width; j += 10) {
          ctx.lineTo(j, i + Math.sin((1 + r) * j / 10 ) * waveHeight);
        }
        ctx.stroke();
      }
    }

    function drawOutline() {
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.moveTo(70,                   55  - 50); //top left
      ctx.lineTo(70,                   420 - 50);
      ctx.lineTo(20,                   420 - 50);
      ctx.lineTo(20,                   555 - 50);
      ctx.lineTo(55,                   555 - 50);
      ctx.lineTo(55,                   canvasDim.height - 30);
      ctx.lineTo(canvasDim.width - 55, canvasDim.height - 30);
      ctx.lineTo(canvasDim.width - 55, 555 - 50);
      ctx.lineTo(canvasDim.width - 20, 555 - 50);
      ctx.lineTo(canvasDim.width - 20, 420 - 50);
      ctx.lineTo(canvasDim.width - 70, 420 - 50);
      ctx.lineTo(canvasDim.width - 70, 55  - 50);
      ctx.closePath();
      ctx.fillStyle = 'rgb(0,0,0,0.01)'
      ctx.fill();
      ctx.strokeStyle = 'rgb(0,0,0,0.04)';
      ctx.stroke();
    }

    function fillTextMultiLine(ctx, text, x, y) {
      var lineHeight = ctx.measureText("M").width * 1.2;
      var lines = text.split("\n");
      for (var i = 0; i < lines.length; ++i) {
        ctx.fillText(lines[i], x, y);
        y += lineHeight;
      }
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
        if (label.text.length > 60){
          fillTextMultiLine(ctx, label.text, label.x + label.width / 2, label.y + label.height / 3)
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
        if (label.text.length > 60){
          fillTextMultiLine(ctx, label.text, label.x + label.width / 2, label.y + label.height / 3)
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
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, heat ? "#D8A0A2" : '#fff', '#000');
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
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, (pumps.has(label.text)) ? '#EABC74' : '#fff', '#000');
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
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, (leds[label.text] > 0) ? `rgba(234, 188, 116, ${leds[label.text]/100 + 0.2})` : '#fff', '#000');
        ctx.stroke();
        ctx.fillStyle = '#000';
        ctx.fillText(label.text, label.x + label.width / 2, label.y + label.height / 2);
      });
    }

    function drawBioreactor() {
      ctx.clearRect(0, 0, canvasDim.width, canvasDim.height);
      // drawOutline
      drawOutline()

      // Draw bioreactor body
      drawRoundedRect(bioreactor.x, bioreactor.y, bioreactor.width, bioreactor.height, bioreactor.cornerRadius, 'rgb(244,244,244)', '#000');

      // Draw liquid level with turbidity
      drawTurbidLiquid(bioreactor.x, Math.max(bioreactor.y + bioreactor.height - liquidLevel, bioreactor.y), bioreactor.width, Math.min(liquidLevel,  bioreactor.height), bioreactor.cornerRadius, nOD);

      // Draw stir bar
      const angle = (2 * Math.PI / (130 * fps / (rpm) ) ) * stirBarFrame.current;
      const width = bioreactor.stirBar.maxWidth * Math.abs(Math.cos(angle)) + 10;
      drawRoundedRect(bioreactor.stirBar.x + (bioreactor.stirBar.maxWidth - width) / 2, bioreactor.stirBar.y, width, bioreactor.stirBar.height, bioreactor.stirBar.radius, '#fff', '#000');

      // Draw labeled rectangles
      drawLabeledLeds(ledsRects);
      drawLabeledPumps(pumpsRects);
      drawLabeledRectangles(dynamicRects);
      drawLabeledHeat(heaterRec);
      if (pumps.size) {
        drawWarning(warningRects);
      }
    }

    function update() {

      // request another frame

      animationFrameId = window.requestAnimationFrame(update);

      // calc elapsed time since last loop

      now = window.performance.now()
      elapsed = now - then;

      // if enough time has elapsed, draw the next frame
      if (elapsed > fpsInterval) {

          // Get ready for next frame by setting then=now, but also adjust for your
          // specified fpsInterval not being a multiple of RAF's interval (16.7ms)
          then = now - (elapsed % fpsInterval);

          stirBarFrame.current = (stirBarFrame.current + 1)  % Math.round(130 * fps / (rpm) );

          drawBioreactor();

      }


    }

    function startAnimating() {
      then = window.performance.now()
      update();
    }
    startAnimating()
    // Cleanup on component unmount
    return () => {
        window.cancelAnimationFrame(animationFrameId);
    };
  }, [rpm, temperature, nOD, leds, pumps, volume, heat]);

  return (
    <div>
      <canvas style={{display: "block", margin: "0 auto 0 auto"}} ref={canvasRef} width={canvasDim.width} height={canvasDim.height} />
    </div>
  )}

export default Bioreactor40Diagram;
