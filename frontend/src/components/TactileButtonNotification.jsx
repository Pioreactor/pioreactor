import React from "react";
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import { useMQTT } from '../providers/MQTTContext';

import Snackbar from '@mui/material/Snackbar';

const FAILSAFE_AUTO_HIDE_MS = 15000;

function TactileButtonNotification() {
  const [unit, setUnit] = React.useState("")
  const [open, setOpen] = React.useState(false)
  const {client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const topic = "pioreactor/+/$experiment/monitor/button_down"

  const handleClose = (_event, reason) => {
    if (reason === "clickaway") {
      return;
    }
    setOpen(false);
  };

  React.useEffect(() => {
    if (client) {
      subscribeToTopic(topic, onMessage, "TactileButtonNotification");
      return () => unsubscribeFromTopic(topic, "TactileButtonNotification");
    }
  }, [client]);

  const onMessage = (topic, msg) => {
    if (msg.toString() === "True"){
      var unit = topic.toString().split("/")[1]
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
      autoHideDuration={FAILSAFE_AUTO_HIDE_MS}
      onClose={handleClose}
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      key={"button-tactile-snackbar"}
      transitionDuration={{enter: 10}}
    >
    <Alert severity="info" variant="filled" icon={false} onClose={handleClose}>
      <AlertTitle style={{fontSize: 30}}>{unit}</AlertTitle>
      Holding <b>{unit}</b>'s button down
    </Alert>
    </Snackbar>
)}

export default TactileButtonNotification;
