import React from "react";
import { Client } from "paho-mqtt";
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

    const onMessageArrived = (msg) => {
      if (msg.payloadString === "True"){
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

    var client
    if (config.remote && config.remote.ws_url) {
      client = new Client(
        `ws://${config.remote.ws_url}/`,
        "webui_TactileButtonNotification" + Math.floor(Math.random()*10000)
      )}
    else {
      client = new Client(
        `${config['cluster.topology']['leader_address']}`, 9001,
        "webui_TactileButtonNotification" + Math.floor(Math.random()*10000)
      );
    }
    client.connect({userName: 'pioreactor', password: 'raspberry', keepAliveInterval: 60 * 15, onSuccess: onSuccess, timeout: 180, reconnect: true});
    client.onMessageArrived = onMessageArrived;

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
