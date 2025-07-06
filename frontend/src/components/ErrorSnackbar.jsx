import React from "react";
import Alert from '@mui/material/Alert';
import Snackbar from '@mui/material/Snackbar';
import AlertTitle from '@mui/material/AlertTitle';
import { useMQTT } from '../providers/MQTTContext';
import { useExperiment } from '../providers/ExperimentContext';

function ErrorSnackbar() {
  const [open, setOpen] = React.useState(false)
  const [unit, setUnit] = React.useState("")
  const [msg, setMsg] = React.useState("")
  const [level, setLevel] = React.useState("error")
  const [task, setTask] = React.useState("")
  const {client, subscribeToTopic } = useMQTT();
  const { experimentMetadata } = useExperiment();

  React.useEffect(() => {
    if (client && experimentMetadata){
      subscribeToTopic([`pioreactor/+/${experimentMetadata.experiment}/logs/app/error`,
                        `pioreactor/+/${experimentMetadata.experiment}/logs/app/warning`,
                        `pioreactor/+/${experimentMetadata.experiment}/logs/app/notice`,
                        `pioreactor/+/$experiment/logs/app/error`,
                        `pioreactor/+/$experiment/logs/app/warning`,
                        `pioreactor/+/$experiment/logs/app/notice`],
                      onMessage, "ErrorSnackbar")
    }

  },[client, experimentMetadata])

  const onMessage = (topic, message, packet) => {
      if (!message || !topic) return;

      if (!topic.toString().endsWith("/ui")){
        const payload = JSON.parse(message.toString())
        const unit = topic.toString().split("/")[1]
        setMsg(payload.message)
        setTask(payload.task)
        setLevel(payload.level === "NOTICE" ? "SUCCESS" : payload.level)
        setUnit(unit === "$broadcast" ? "All Pioreactors" : unit)
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
      <AlertTitle style={{fontSize: 15}}>{task} encountered a{level==="ERROR" ? 'n' : ''} {level.toLowerCase()} in {unit}</AlertTitle>
      <span style={{whiteSpace: 'pre-wrap'}}>{msg}</span>
    </Alert>
    </Snackbar>
)}

export default ErrorSnackbar;
