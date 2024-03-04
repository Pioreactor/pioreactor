import React from "react";
import mqtt from 'mqtt'
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import {getConfig, getRelabelMap} from "../utilities"

import Snackbar from '@mui/material/Snackbar';

function TactileButtonNotification(props) {
  const [unit, setUnit] = React.useState("")
  const [renamedUnit, setRenamedUnit] = React.useState("")
  const [open, setOpen] = React.useState(false)
  const [relabelMap, setRelabelMap] = React.useState({})
  const [config, setConfig] = React.useState({})

  React.useEffect(() => {
    getRelabelMap(setRelabelMap)
    getConfig(setConfig)
  }, [])

  React.useEffect(() => {
    if (!config['cluster.topology']){
      return
    }

    const onMessage = (msg) => {
      if (msg.toString() === "True"){
        var unit = msg.topic.split("/")[1]
        setUnit(unit)
        try {
          setRenamedUnit(relabelMap[unit])
        }
        catch {}
        setOpen(true)
      }
      else {
        setOpen(false)
      }
    }

    const onSuccess = () => {
      client.subscribe(
      [
        "pioreactor",
        "+",
        "$experiment",
        "monitor",
        "button_down"
      ].join("/"),
      { qos: 1 }
      )
    }

    const userName = config.mqtt.username || "pioreactor"
    const password = config.mqtt.password || "raspberry"
    const brokerUrl = `${config.mqtt.ws_protocol}://${config.mqtt.broker_address}:${config.mqtt.broker_ws_port || 9001}/mqtt`;

    const client = mqtt.connect(brokerUrl, {
      username: userName,
      password: password,
    });
    client.on("connect", () => onSuccess() )
    client.on("message", (topic, message) => {
      onMessage(message);
    });
    client.on('error', function (error) {
      console.log(error)
    });
    return () => {client.end()};

  },[config, relabelMap])

  return (
    <Snackbar
      open={open}
      autoHideDuration={null}
      onClose={() => {}}
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      key={"button-tactile-snackbar"}
      transitionDuration={{enter: 10}}
    >
    <Alert severity="info" variant="filled" icon={false}>
      <AlertTitle style={{fontSize: 30}}>{unit + (renamedUnit ? " / " + renamedUnit : "")}</AlertTitle>
      Holding <b>{unit}</b>'s button down
    </Alert>
    </Snackbar>
)}

export default TactileButtonNotification;
