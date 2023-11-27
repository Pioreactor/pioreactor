import React from "react";
import { Client } from "paho-mqtt";
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import {getConfig, getRelabelMap} from "../utilities"

import Snackbar from '@mui/material/Snackbar';

function ErrorSnackbar(props) {
  const [open, setOpen] = React.useState(false)
  const [renamedUnit, setRenamedUnit] = React.useState("")
  const [unit, setUnit] = React.useState("")
  const [msg, setMsg] = React.useState("")
  const [level, setLevel] = React.useState("error")
  const [task, setTask] = React.useState("")
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

    const onFailure = () => {
      setMsg(`Failed to connect to MQTT. Is configuration for leader_address correct? Currently set to ${config['cluster.topology']['leader_address']}.`)
      setTask("PioreactorUI")
      setLevel("ERROR")
      setUnit(config['cluster.topology']['leader_hostname'])
      setOpen(true)
    }

    const onSuccess = () => {
      client.subscribe(
      [
        "pioreactor",
        "+",
        "+",
        "logs",
        "+"
      ].join("/"),
      { qos: 1 }
      )
    }

    var client
    if (config.remote && config.remote.ws_url) {
      client = new Client(
        `${config.remote.ws_url}/`,
        "webui_ErrorSnackbarNotification" + Math.floor(Math.random()*10000)
      )}
    else {
      client = new Client(
        `${config['cluster.topology']['leader_address']}`, 9001,
        "webui_ErrorSnackbarNotification" + Math.floor(Math.random()*10000)
      );
    }
    client.connect({userName: 'pioreactor', password: 'raspberry', keepAliveInterval: 60 * 15, timeout: 10, onSuccess: onSuccess, onFailure: onFailure});
    client.onMessageArrived = onMessageArrived;

  },[config])

  const onMessageArrived = (message) => {
      const payload = JSON.parse(message.payloadString)

      if ((payload.level === "ERROR" || payload.level === "WARNING" || payload.level === "NOTICE") && (!message.topic.endsWith("/ui"))){
        const unit = message.topic.split("/")[1]
        try {
          setRenamedUnit(relabelMap[unit])
        }
        catch {}
        setMsg(payload.message)
        setTask(payload.task)
        setLevel(payload.level === "NOTICE" ? "SUCCESS" : payload.level)
        setUnit(unit)
        setOpen(true)
      }
    }


  const handleClose = (event, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setOpen(false);
  };


  return (
    <Snackbar
      open={open}
      anchorOrigin={{vertical: "bottom", horizontal: "right"}}
      key="error-snackbar"
      autoHideDuration={14000}
      style={{maxWidth: "500px"}}
      onClose={handleClose}
    >
    <Alert variant="standard" severity={level.toLowerCase()} onClose={handleClose}>
      <AlertTitle style={{fontSize: 15}}>{task} encountered a{level==="ERROR" ? 'n' : ''} {level.toLowerCase()} in {unit + (renamedUnit ? " / " + renamedUnit : "")}</AlertTitle>
      <span style={{whiteSpace: 'pre-wrap'}}>{msg}</span>
    </Alert>
    </Snackbar>
)}

export default ErrorSnackbar;
