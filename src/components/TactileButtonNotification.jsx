import React from "react";
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import { useMQTT } from '../providers/MQTTContext';

import Snackbar from '@mui/material/Snackbar';

function TactileButtonNotification(props) {
  const [unit, setUnit] = React.useState("")
  const [open, setOpen] = React.useState(false)
  const {client, subscribeToTopic } = useMQTT();


  React.useEffect(() => {
    if (client) {
      subscribeToTopic("pioreactor/+/$experiment/monitor/button_down", onMessage)
    }
  },[client])

  const onMessage = (topic, msg, packet) => {
    if (msg.toString() === "True"){
      var unit = msg.topic.split("/")[1]
      setUnit(unit)
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
      <AlertTitle style={{fontSize: 30}}>{unit}</AlertTitle>
      Holding <b>{unit}</b>'s button down
    </Alert>
    </Snackbar>
)}

export default TactileButtonNotification;
