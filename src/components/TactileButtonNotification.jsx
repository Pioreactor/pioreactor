import React from "react";
import { Client } from "paho-mqtt";
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';

import Snackbar from '@mui/material/Snackbar';

function TactileButtonNotification(props) {
  const [unit, setUnit] = React.useState("")
  const [renamedUnit, setRenamedUnit] = React.useState("")
  const [open, setOpen] = React.useState(false)
  const [relabelMap, setRelabelMap] = React.useState({})

  React.useEffect(() => {

    function getRelabelMap() {
        fetch("/api/get_current_unit_labels")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setRelabelMap(data)
        });
      }

    getRelabelMap()
  }, [])

  React.useEffect(() => {
    if (!props.config['cluster.topology']){
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
    if (props.config.remote && props.config.remote.ws_url) {
      client = new Client(
        `ws://${props.config.remote.ws_url}/`,
        "webui_TactileButtonNotification" + Math.random()
      )}
    else {
      client = new Client(
        `${props.config['cluster.topology']['leader_address']}`, 9001,
        "webui_TactileButtonNotification" + Math.random()
      );
    }
    client.connect({onSuccess: onSuccess, timeout: 180, reconnect: true});
    client.onMessageArrived = onMessageArrived;

  },[props.config, relabelMap])

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
      <AlertTitle style={{fontSize: 25}}>{unit + (renamedUnit ? " / " + renamedUnit : "")}</AlertTitle>
      Holding <b>{unit}</b>'s button down
    </Alert>
    </Snackbar>
)}

export default TactileButtonNotification;
