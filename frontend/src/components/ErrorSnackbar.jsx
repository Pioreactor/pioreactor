import React from "react";
import Alert from '@mui/material/Alert';
import Link from '@mui/material/Link';
import AlertTitle from '@mui/material/AlertTitle';
import { useSnackbar } from "notistack";
import { Link as RouterLink } from 'react-router';
import { useMQTT } from '../providers/MQTTContext';
import { useExperiment } from '../providers/ExperimentContext';

const HEAD_LINE_COUNT = 2;
const TAIL_LINE_COUNT = 5;
const AUTO_HIDE_DURATION_MS = 7000;

function createAlertStore() {
  const alerts = new Map();
  const listeners = new Map();

  const notify = (dedupeKey) => {
    const keyListeners = listeners.get(dedupeKey);
    if (!keyListeners) return;
    keyListeners.forEach((listener) => listener());
  };

  return {
    get(dedupeKey) {
      return alerts.get(dedupeKey) ?? null;
    },
    set(dedupeKey, alert) {
      alerts.set(dedupeKey, alert);
      notify(dedupeKey);
    },
    delete(dedupeKey) {
      alerts.delete(dedupeKey);
      notify(dedupeKey);
    },
    clear() {
      const dedupeKeys = Array.from(alerts.keys());
      alerts.clear();
      dedupeKeys.forEach(notify);
    },
    forEach(callback) {
      alerts.forEach(callback);
    },
    subscribe(dedupeKey, listener) {
      const keyListeners = listeners.get(dedupeKey) ?? new Set();
      keyListeners.add(listener);
      listeners.set(dedupeKey, keyListeners);

      return () => {
        keyListeners.delete(listener);
        if (keyListeners.size === 0) {
          listeners.delete(dedupeKey);
        }
      };
    },
  };
}

function formatLogMessage(msg) {
  const lines = msg.split(/\r?\n/);
  if (lines.length <= HEAD_LINE_COUNT + TAIL_LINE_COUNT) {
    return msg;
  }

  const head = lines.slice(0, HEAD_LINE_COUNT);
  const tail = lines.slice(-TAIL_LINE_COUNT);
  return [...head, "...", ...tail].join("\n");
}

function getAlertTitle(taskName, alertLevel, unitName) {
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
}

function getDedupeKey({ unit, experiment, task, level, message }) {
  return JSON.stringify([unit, experiment, task, level, message]);
}

const LogAlertContent = React.forwardRef(function LogAlertContent({
  alertStore,
  dedupeKey,
  snackbarKey,
  closeSnackbar,
  alertLevel,
  alertTitle,
  formattedMessage,
  showLogsHelper,
  logsRoute,
  logsLabel,
}, ref) {
  const activeAlert = React.useSyncExternalStore(
    React.useCallback(
      (onStoreChange) => alertStore.subscribe(dedupeKey, onStoreChange),
      [alertStore, dedupeKey],
    ),
    React.useCallback(() => alertStore.get(dedupeKey), [alertStore, dedupeKey]),
  );
  const count = activeAlert?.count ?? 1;

  return (
    <div ref={ref} style={{maxWidth: "500px"}}>
      <Alert
        variant="standard"
        severity={alertLevel.toLowerCase()}
        onClose={() => closeSnackbar(snackbarKey)}
      >
        <AlertTitle style={{fontSize: 15}}>{alertTitle}</AlertTitle>
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
              onClick={() => closeSnackbar(snackbarKey)}
            >
              {logsLabel}
            </Link>
          </div>
        )}
        {count > 1 && (
          <div
            style={{
              color: "rgba(0, 0, 0, 0.6)",
              fontSize: 12,
              lineHeight: 1.4,
              marginTop: "10px",
              textAlign: "left",
            }}
          >
            Repeated {count}x
          </div>
        )}
      </Alert>
    </div>
  );
});

function scheduleAlertClose(alertStore, dedupeKey, closeSnackbar) {
  const activeAlert = alertStore.get(dedupeKey);
  if (!activeAlert) return;

  if (activeAlert.timeoutId !== null) {
    clearTimeout(activeAlert.timeoutId);
  }

  const timeoutId = setTimeout(() => {
    const latestAlert = alertStore.get(dedupeKey);
    if (latestAlert) {
      closeSnackbar(latestAlert.snackbarKey);
    }
  }, AUTO_HIDE_DURATION_MS);

  alertStore.set(dedupeKey, { ...activeAlert, timeoutId });
}

function ErrorSnackbar() {
  const {client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const { experimentMetadata } = useExperiment();
  const { enqueueSnackbar, closeSnackbar } = useSnackbar();
  const alertStoreRef = React.useRef(null);
  if (alertStoreRef.current === null) {
    alertStoreRef.current = createAlertStore();
  }

  const enqueueLogAlert = React.useCallback(({ unit, experiment, task, level, message }) => {
    const alertStore = alertStoreRef.current;
    const alertLevel = level === "NOTICE" ? "SUCCESS" : level;
    const displayUnit = unit === "$broadcast" ? "All Pioreactors" : unit;
    const formattedMessage = formatLogMessage(message);
    const dedupeKey = getDedupeKey({ unit, experiment, task, level, message });
    const previousAlert = alertStore.get(dedupeKey);
    const count = (previousAlert?.count ?? 0) + 1;
    const showLogsHelper = ["ERROR", "WARNING"].includes(alertLevel);
    const logsRoute = experiment === "$experiment" ? "/system-logs" : "/logs";
    const logsLabel = experiment === "$experiment" ? "View System Logs" : "View Experiment Logs";
    const alertTitle = getAlertTitle(task, alertLevel, displayUnit);

    if (previousAlert) {
      if (previousAlert.timeoutId !== null) {
        clearTimeout(previousAlert.timeoutId);
      }
      alertStore.set(dedupeKey, { ...previousAlert, count, timeoutId: null });
      scheduleAlertClose(alertStore, dedupeKey, closeSnackbar);
      return;
    }

    const snackbarKey = enqueueSnackbar(`${task}:${alertLevel}:${displayUnit}:${formattedMessage}`, {
      anchorOrigin: {vertical: "bottom", horizontal: "right"},
      persist: true,
      TransitionProps: { direction: "up" },
      content: (key) => (
        <LogAlertContent
          alertStore={alertStore}
          dedupeKey={dedupeKey}
          snackbarKey={key}
          closeSnackbar={closeSnackbar}
          alertLevel={alertLevel}
          alertTitle={alertTitle}
          formattedMessage={formattedMessage}
          showLogsHelper={showLogsHelper}
          logsRoute={logsRoute}
          logsLabel={logsLabel}
        />
      ),
      onClose: (_event, _reason, key) => {
        const activeAlert = alertStore.get(dedupeKey);
        if (activeAlert?.snackbarKey === key) {
          if (activeAlert.timeoutId !== null) {
            clearTimeout(activeAlert.timeoutId);
          }
          alertStore.delete(dedupeKey);
        }
      },
    });

    alertStore.set(dedupeKey, { snackbarKey, count, timeoutId: null });
    scheduleAlertClose(alertStore, dedupeKey, closeSnackbar);
  }, [closeSnackbar, enqueueSnackbar]);

  const onMessage = React.useCallback((topic, message, _packet) => {
    if (!message || !topic) return;

    const topicString = topic.toString();
    if (topicString.endsWith("/ui")) {
      return;
    }

    let payload;
    try {
      payload = JSON.parse(message.toString());
    } catch {
      return;
    }

    const [, unit, experimentFromTopic] = topicString.split("/");
    enqueueLogAlert({
      unit: unit ?? "",
      experiment: experimentFromTopic ?? "",
      task: String(payload.task ?? ""),
      level: String(payload.level ?? "NOTICE").toUpperCase(),
      message: String(payload.message ?? ""),
    });
  }, [enqueueLogAlert]);

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
  }, [client, experimentMetadata, onMessage, subscribeToTopic, unsubscribeFromTopic]);

  React.useEffect(() => {
    const alertStore = alertStoreRef.current;
    return () => {
      alertStore.forEach(({ snackbarKey, timeoutId }) => {
        if (timeoutId !== null) {
          clearTimeout(timeoutId);
        }
        closeSnackbar(snackbarKey);
      });
      alertStore.clear();
    };
  }, [closeSnackbar]);

  return null;
}

export default ErrorSnackbar;
