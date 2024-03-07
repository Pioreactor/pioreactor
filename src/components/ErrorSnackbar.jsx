import React from "react";
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import {getRelabelMap} from "../utilities"
import { useMQTT } from '../MQTTContext';
import Snackbar from '@mui/material/Snackbar';

function ErrorSnackbar(props) {
  const [open, setOpen] = React.useState(false)
  const [renamedUnit, setRenamedUnit] = React.useState("")
  const [unit, setUnit] = React.useState("")
  const [msg, setMsg] = React.useState("")
  const [level, setLevel] = React.useState("error")
  const [task, setTask] = React.useState("")
  const [relabelMap, setRelabelMap] = React.useState({})
  const {client, subscribeToTopic } = useMQTT();

  const config = props.config


  React.useEffect(() => {
    getRelabelMap(setRelabelMap)
  }, [])

  React.useEffect(() => {
    if (!config.mqtt){
      return
    }

    subscribeToTopic("pioreactor/+/+/logs/+", onMessage)

  },[config, client])

  const onMessage = (topic, message, packet) => {
      const payload = JSON.parse(message.toString())
      if ((payload.level === "ERROR" || payload.level === "WARNING" || payload.level === "NOTICE") && (!topic.toString().endsWith("/ui"))){
        const unit = topic.toString().split("/")[1]
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
