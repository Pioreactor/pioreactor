import React from "react";
import Alert from '@mui/material/Alert';
import Link from '@mui/material/Link';
import Snackbar from './Snackbar';
import AlertTitle from '@mui/material/AlertTitle';
import { Link as RouterLink } from 'react-router';
import { useMQTT } from '../providers/MQTTContext';
import { useExperiment } from '../providers/ExperimentContext';

function ErrorSnackbar() {
  const HEAD_LINE_COUNT = 4;
  const TAIL_LINE_COUNT = 4;
  const [open, setOpen] = React.useState(false)
  const [unit, setUnit] = React.useState("")
  const [msg, setMsg] = React.useState("")
  const [level, setLevel] = React.useState("error")
  const [task, setTask] = React.useState("")
  const [experiment, setExperiment] = React.useState("")
  const {client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const { experimentMetadata } = useExperiment();

  const getAlertTitle = (taskName, alertLevel, unitName) => {
    if (!taskName || !alertLevel || !unitName) return "";

    switch (alertLevel) {
      case "ERROR":
        return `${taskName} failed in ${unitName}`;
      case "WARNING":
        return `${taskName} needs attention in ${unitName}`;
      case "SUCCESS":
        return `${taskName} update in ${unitName}`;
      default:
        return `${taskName} update in ${unitName}`;
    }
  };

  React.useEffect(() => {
    if (!client || !experimentMetadata) {
      return undefined;
    }

    const topics = [
      `pioreactor/+/${experimentMetadata.experiment}/logs/+/error`,
      `pioreactor/+/${experimentMetadata.experiment}/logs/+/warning`,
      `pioreactor/+/${experimentMetadata.experiment}/logs/+/notice`,
      `pioreactor/+/$experiment/logs/+/error`,
      `pioreactor/+/$experiment/logs/+/warning`,
      `pioreactor/+/$experiment/logs/+/notice`,
    ];

    subscribeToTopic(topics, onMessage, "ErrorSnackbar");

    return () => {
      unsubscribeFromTopic(topics, "ErrorSnackbar");
    };
  }, [client, experimentMetadata, subscribeToTopic, unsubscribeFromTopic])

  const onMessage = (topic, message, _packet) => {
      if (!message || !topic) return;

      if (!topic.toString().endsWith("/ui")){
        const payload = JSON.parse(message.toString())
        const [_, unit, experimentFromTopic] = topic.toString().split("/")
        setMsg(payload.message)
        setTask(payload.task)
        setLevel(payload.level === "NOTICE" ? "SUCCESS" : payload.level)
        setUnit(unit === "$broadcast" ? "All Pioreactors" : unit)
        setExperiment(experimentFromTopic)
        setOpen(true)
      }
    }


  const handleClose = (_event, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setOpen(false);
  };

  const formattedMessage = React.useMemo(() => {
    const lines = msg.split(/\r?\n/);
    if (lines.length <= HEAD_LINE_COUNT + TAIL_LINE_COUNT) {
      return msg;
    }

    const head = lines.slice(0, HEAD_LINE_COUNT);
    const tail = lines.slice(-TAIL_LINE_COUNT);
    return [...head, "...", ...tail].join("\n");
  }, [msg]);

  const showLogsHelper = ["ERROR", "WARNING"].includes(level);
  const logsRoute = experiment === "$experiment" ? "/system-logs" : "/logs";
  const logsLabel = experiment === "$experiment" ? "View System Logs" : "View Logs";


  return (
    <Snackbar
      open={open}
      anchorOrigin={{vertical: "bottom", horizontal: "right"}}
      key="error-snackbar"
      autoHideDuration={14000}
      style={{maxWidth: "500px"}}
      message={`${task}:${level}:${unit}:${formattedMessage}`}
      onClose={handleClose}
    >
    <Alert variant="standard" severity={level.toLowerCase()} onClose={handleClose}>
      <AlertTitle style={{fontSize: 15}}>{getAlertTitle(task, level, unit)}</AlertTitle>
      <span
        style={{
          whiteSpace: "pre-wrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          WebkitLineClamp: 10,
          wordBreak: "break-word",
        }}
      >
        {formattedMessage}
      </span>
      {showLogsHelper && (
        <div style={{ marginTop: 8 }}>
          <Link
            component={RouterLink}
            to={logsRoute}
            underline="always"
            color="info.main"
            sx={{ cursor: "pointer", fontWeight: 500 }}
            onClick={handleClose}
          >
            {logsLabel}
          </Link>
        </div>
      )}
    </Alert>
    </Snackbar>
)}

export default ErrorSnackbar;
