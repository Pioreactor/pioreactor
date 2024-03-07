import React from "react";
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import {getRelabelMap} from "../utilities"
import { useMQTT } from '../MQTTContext';

import Snackbar from '@mui/material/Snackbar';

function TactileButtonNotification(props) {
  const [unit, setUnit] = React.useState("")
  const [renamedUnit, setRenamedUnit] = React.useState("")
  const [open, setOpen] = React.useState(false)
  const [relabelMap, setRelabelMap] = React.useState({})
  const config = props.config
  const {client, subscribeToTopic } = useMQTT();

  React.useEffect(() => {
    getRelabelMap(setRelabelMap)
  }, [])

  React.useEffect(() => {
    if (!config['cluster.topology']){
      return
    }

    subscribeToTopic("pioreactor/+/$experiment/monitor/button_down", onMessage)

  },[config, relabelMap, client])

  const onMessage = (topic, msg, packet) => {
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
