import React from "react";
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import { useMQTT } from '../providers/MQTTContext';

import Snackbar from '@mui/material/Snackbar';

function TactileButtonNotification() {
  const [unit, setUnit] = React.useState("")
  const [open, setOpen] = React.useState(false)
  const {client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const topic = "pioreactor/+/$experiment/monitor/button_down"

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
