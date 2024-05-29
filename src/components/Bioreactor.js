import React, { useRef, useEffect, useState } from 'react';
import { useMQTT } from '../providers/MQTTContext';

const canvasDim = {
  height: 600,
  width: 400
}

function roundTo1(x){
  return `${Math.round(x * 10) / 10}`
}

function binFloat(value, binSize) {
    return Math.floor(value / binSize) * binSize;
}

const bioreactor = {
  width: 200,
  height: 400,
  x: (canvasDim.width - 200) / 2,
  y: (canvasDim.height - 400) / 2 - 30,
  cornerRadius: 20,
  stirBar: {
    maxWidth: 70,
    height: 10,
    x: (canvasDim.width - 70) / 2,
    y: (canvasDim.height - 20) / 2 + 150,
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


const BioreactorDiagram = ({experiment, unit, config}) => {
  const {client, subscribeToTopic } = useMQTT();

  const canvasRef = useRef(null);
  const stirBarFrame = useRef(0)
  const [rpm, setRpm] = useState(null);
  const [temperature, setTemperature] = useState(null);
  const [nOD, setNOD] = useState(null);
  const [leds, setLeds] = useState({A: 0, B: 0, C: 0, D: 0});
  const [pumps, setPumps] = useState(new Set([]));
  const [heat, setHeat] = useState(false);
  const [volume, setVolume] = useState(14);

  useEffect(() => {
    if (Object.keys(config).length){
      setVolume(config?.bioreactor?.initial_volume_ml)
    }
  }, [config])



  function onMessage(topic, message, packet) {
    const topicString = topic.toString()
    const messageString = message.toString()

    if (topicString.endsWith("pwms/dc")) {
      const dcs = JSON.parse(messageString) // {17: 10.3, 12: 34.3}

      const pumps = new Set([])
      var rpm = null

      for (const pin of  Object.keys(dcs)) {
        const pwmOutput = PIN_TO_PWM[pin]
        // now what load is that:
        const load = config.PWM[pwmOutput]

        switch (load){
          case "stirring":
            rpm = 500
            break
          case "media":
            pumps.add('media')
            break
          case "alt_media":
            pumps.add('alt-media')
            break
          case "waste":
            pumps.add('waste')
            break
          default:
            break
        }
      }
      setPumps(pumps)
      setRpm(rpm)

    } else if (topicString.endsWith("temperature_control/temperature")){
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
    } else if (topicString.endsWith("dosing_automation/vial_volume")){
      if (messageString === "") {
        //
      } else {
        setVolume(parseFloat(messageString))
      }
    } else if (topicString.endsWith("temperature_control/automation_name")){
      if (messageString === "") {
        setHeat(false)
      } else {
        setHeat(messageString!=="only_record_temperature")
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
    if (client && experiment){
      subscribeToTopic(`pioreactor/${unit}/${experiment}/temperature_control/temperature`, onMessage, "BioreactorDiagram");
      subscribeToTopic(`pioreactor/${unit}/${experiment}/growth_rate_calculating/od_filtered`, onMessage, "BioreactorDiagram");
      subscribeToTopic(`pioreactor/${unit}/${experiment}/leds/intensity`, onMessage, "BioreactorDiagram");
      subscribeToTopic(`pioreactor/${unit}/${experiment}/dosing_automation/vial_volume`, onMessage, "BioreactorDiagram");
      subscribeToTopic(`pioreactor/${unit}/${experiment}/temperature_control/automation_name`, onMessage, "BioreactorDiagram");
      subscribeToTopic(`pioreactor/${unit}/${experiment}/pwms/dc`, onMessage, "BioreactorDiagram");
    }
  }, [client, experiment])

  useEffect(() => {
    let animationFrameId;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const liquidLevel = volume / 20 * 350 // max is 350px at 20ml, 0ml is 0px.
    const bottomOfWasteTube = bioreactor.height - (config?.bioreactor?.max_volume_ml || 14) / 20 * 350 + 20

    const ledsRects = [
      { text: 'B', x: 50,  y: 370, width: 40, height: 30, radius: 5 },
      { text: 'D', x: 310, y: 370, width: 40, height: 30, radius: 5 },
      { text: 'A', x: 50,  y: 320, width: 40, height: 30, radius: 5 },
      { text: 'C', x: 310, y: 320, width: 40, height: 30, radius: 5 },
    ]

    const heaterRec = [
      { text: 'heat', x: 100,  y: 477, width: 200, height: 20, radius: 3 },
    ]

    const pumpsRects = [
      { text: 'waste', x: bioreactor.x + bioreactor.width * 3 / 4, y: bioreactor.y - 20, width: 20, height: bottomOfWasteTube, radius: 3 },
      { text: 'media', x: bioreactor.x + bioreactor.width / 2, y: bioreactor.y - 20, width: 20, height: 100, radius: 3 },
      { text: 'alt-media', x: bioreactor.x + bioreactor.width / 4, y: bioreactor.y - 20, width: 20, height: 100, radius: 3 },
    ];

    const warningRects = [
      { text: '⚠ liquid level above may not be an accurate\nreflection of the vial - observe carefully.', x: 50, y: 520, width: 300, height: 45, radius: 5 },
    ]

    var dynamicRects = []
    if (temperature){
      dynamicRects.push({ text: `Temp: ${roundTo1(temperature)}°C`, x: 110, y: 260, width: 90, height: 30, radius: 5 })
    }
    if (nOD){
      dynamicRects.push({ text: `nOD: ${roundTo1(nOD)}`, x: 210, y: 260, width: 80, height: 30, radius: 5 })
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
      // Draw the liquid with rounded corners
      drawRoundedRect(x, y, width, height, radius, '#F5DEB3', '#000');

      if (!turbidity){
        return
      }

      // Draw wavy lines to simulate turbidity
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)';
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
      ctx.moveTo(70,                   60  - 30); //top left
      ctx.lineTo(70,                   320 - 30);
      ctx.lineTo(20,                   320 - 30);
      ctx.lineTo(20,                   455 - 30);
      ctx.lineTo(55,                   455 - 30);
      ctx.lineTo(55,                   540 - 30);
      ctx.lineTo(canvasDim.width - 55, 540 - 30);
      ctx.lineTo(canvasDim.width - 55, 455 - 30);
      ctx.lineTo(canvasDim.width - 20, 455 - 30);
      ctx.lineTo(canvasDim.width - 20, 320 - 30);
      ctx.lineTo(canvasDim.width - 70, 320 - 30);
      ctx.lineTo(canvasDim.width - 70, 60  - 30);
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
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, 'rgb(255, 244, 229)', 'rgb(255, 244, 229)');
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
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, heat ? "#ff9601" : '#fff', '#000');
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
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, (pumps.has(label.text)) ? '#FFEC8A' : '#fff', '#000');
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
        drawRoundedRect(label.x, label.y, label.width, label.height, label.radius, (leds[label.text] > 0) ? '#FFEC8A' : '#fff', '#000');
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
      drawRoundedRect(bioreactor.x, bioreactor.y, bioreactor.width, bioreactor.height, bioreactor.cornerRadius, '#f8f8f8', '#000');

      // Draw liquid level with turbidity
      drawTurbidLiquid(bioreactor.x, bioreactor.y + bioreactor.height - liquidLevel, bioreactor.width, liquidLevel, bioreactor.cornerRadius, nOD);

      // Draw stir bar
      const angle = (2 * Math.PI / (200 * 60 / (rpm/2) ) ) * stirBarFrame.current;
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
      stirBarFrame.current = (stirBarFrame.current + 1)  % Math.round(200 * 60/ (rpm/2) );

      drawBioreactor();
      animationFrameId = window.requestAnimationFrame(update);
    }

    // Start the animation
    update();

    // Cleanup on component unmount
    return () => {
        window.cancelAnimationFrame(animationFrameId);
    };
  }, [rpm, temperature, nOD, leds, pumps, volume, heat]);

  return (
    <div>
      <canvas ref={canvasRef} width={canvasDim.width} height={canvasDim.height} />
    </div>
  )}

export default BioreactorDiagram;
