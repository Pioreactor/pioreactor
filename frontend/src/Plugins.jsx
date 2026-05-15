import Avatar from "boring-avatars";
import React from "react";
import Divider from "@mui/material/Divider";

import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import { Alert, Typography } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import Snackbar from "./components/Snackbar";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemAvatar from "@mui/material/ListItemAvatar";
import ListItemSecondaryAction from "@mui/material/ListItemSecondaryAction";
import ListItemText from "@mui/material/ListItemText";
import DeleteIcon from "@mui/icons-material/Delete";
import CircularProgress from "@mui/material/CircularProgress";
import { Link, useParams, useNavigate } from "react-router";
import { fetchTaskResult } from "./utils/tasks";
import { styled } from "@mui/material/styles";
import PioreactorsIcon from "./components/PioreactorsIcon";

const BROADCAST_TARGET = "$broadcast";
const PLUGIN_ROW_CONTENT_INSET = "2%";
const PLUGIN_ROW_ACTION_SX = {
  display: { xs: "contents", md: "block" },
  right: { md: `calc(${PLUGIN_ROW_CONTENT_INSET} + 16px)` },
};

const ListItemStyled = styled(ListItem)(() => ({
  "&:nth-of-type(odd)": {
    backgroundColor: "#F7F7F7",
  },
  "&:nth-of-type(even)": {
    backgroundColor: "white",
  },
  paddingLeft: `calc(${PLUGIN_ROW_CONTENT_INSET} + 16px)`,
  paddingRight: `calc(${PLUGIN_ROW_CONTENT_INSET} + 16px)`,
}));

function PageHeader() {
  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h5" component="h2">
          <Box sx={{ fontWeight: "fontWeightBold" }}>Plugins</Box>
        </Typography>
      </Box>
      <Divider sx={{ marginTop: "0px", marginBottom: "15px" }} />
    </Box>
  );
}

function getTargetLabel(target) {
  return target === BROADCAST_TARGET ? "All Pioreactors" : target;
}

function isRealUnitTarget(target, units) {
  return Boolean(target) && units.includes(target);
}

function makeTaskKey(action, source, pluginName, target) {
  return `${action}:${source}:${pluginName}:${target}`;
}

function getTaskStatusLabel(task) {
  if (!task) {
    return "";
  }

  if (task.status === "failed") {
    return "Failed";
  }

  if (task.status === "succeeded") {
    return task.action === "uninstall" ? "Removed" : "Installed";
  }

  return task.action === "uninstall" ? "Uninstalling" : "Installing";
}

function PluginAvatar({ name, source = "community" }) {
  const colors =
    source === "installed"
      ? ["#5332ca", "#94ccc1", "#d8535e", "#f0b250", "#e5e5e5"]
      : ["#5332ca", "#856edb", "#94ccc1", "#d8535e", "#f0b250", "#e5e5e5"];

  return <Avatar name={`${name}${source}`} size={40} colors={colors} variant="bauhaus" />;
}

function TaskStatusText({ task }) {
  if (!task) {
    return null;
  }

  const label = getTaskStatusLabel(task);
  const color = task.status === "failed" ? "error" : "text.secondary";

  return (
    <Typography
      variant="caption"
      component="span"
      color={color}
      sx={{ display: "block", mt: 0.5 }}
    >
      {label} on {getTargetLabel(task.target)}
      {task.status === "failed" && task.message ? `: ${task.message}` : ""}
    </Typography>
  );
}

function InstallButton({
  pluginName,
  selectedTarget,
  isInstalled,
  installedStatePending,
  task,
  onInstall,
  ariaLabel,
}) {
  const isRunning = task?.status === "running";
  const isFailed = task?.status === "failed";
  const disabled =
    !selectedTarget || isRunning || installedStatePending || (!isFailed && isInstalled);
  const broadcastTarget = selectedTarget === BROADCAST_TARGET

  let buttonText = broadcastTarget ? "Install across cluster" : "Install";
  if (isRunning) {
    buttonText = "Installing";
  } else if (installedStatePending) {
    buttonText = "Checking";
  } else if (!isFailed && isInstalled) {
    buttonText = "Installed";
  } else if (isFailed) {
    buttonText = "Retry";
  }

  return (
    <Button
      variant="outlined"
      color="primary"
      size="small"
      aria-label={ariaLabel}
      onClick={() => onInstall(pluginName)}
      disabled={disabled}
      sx={{ ml: "3px", textTransform: "none", minWidth: 92 }}
      startIcon={isRunning ? <CircularProgress color="inherit" size={14} /> : undefined}
    >
      {buttonText}
    </Button>
  );
}

function ListSuggestedPlugins({
  selectedTarget,
  installedPlugins,
  installedStatePending,
  getTask,
  onInstall,
}) {
  const [availablePlugins, setSuggestedPlugins] = React.useState([]);
  const [isSuggestedPluginsLoading, setIsSuggestedPluginsLoading] = React.useState(true);
  const [suggestedPluginsFetchError, setSuggestedPluginsFetchError] = React.useState("");

  React.useEffect(() => {
    let isActive = true;

    async function getData() {
      setIsSuggestedPluginsLoading(true);
      setSuggestedPluginsFetchError("");

      try {
        const response = await fetch(
          "https://raw.githubusercontent.com/Pioreactor/list-of-plugins/main/plugins.json",
        );

        if (!response.ok) {
          throw new Error(`Unable to load community plugins (HTTP ${response.status}).`);
        }

        const payload = await response.json();
        const suggestedPlugins = Array.isArray(payload) ? payload : [];

        if (!isActive) {
          return;
        }

        setSuggestedPlugins(suggestedPlugins);
      } catch (e) {
        if (!isActive) {
          return;
        }

        setSuggestedPlugins([]);
        setSuggestedPluginsFetchError(
          e instanceof Error ? e.message : "Unable to load community plugins.",
        );
      } finally {
        if (isActive) {
          setIsSuggestedPluginsLoading(false);
        }
      }
    }

    getData();

    return () => {
      isActive = false;
    };
  }, []);

  return (
    <Box sx={{ mb: "15px", width: "100%" }}>
      {isSuggestedPluginsLoading && (
        <Box sx={{ textAlign: "center", marginBottom: "24px", marginTop: "24px" }}>
          <CircularProgress size={24} />
        </Box>
      )}

      {!isSuggestedPluginsLoading && suggestedPluginsFetchError && (
        <Box sx={{ textAlign: "center", marginBottom: "24px", marginTop: "24px" }}>
          <Typography variant="body2" component="p" color="error">
            {suggestedPluginsFetchError}
          </Typography>
        </Box>
      )}

      {!isSuggestedPluginsLoading &&
        !suggestedPluginsFetchError &&
        availablePlugins.length === 0 && (
          <Box sx={{ textAlign: "center", marginBottom: "24px", marginTop: "24px" }}>
            <Typography variant="body2" component="p" color="text.secondary">
              No suggested plugins available right now.
            </Typography>
          </Box>
        )}

      {!isSuggestedPluginsLoading &&
        !suggestedPluginsFetchError &&
        availablePlugins.length > 0 && (
          <List>
            {availablePlugins.map((plugin) => {
              const task = getTask("install", "community", plugin.name);
              const isInstalled = installedPlugins.includes(plugin.name);

              return (
                <ListItemStyled key={plugin.name}>
                  <ListItemAvatar>
                    <PluginAvatar name={plugin.name} />
                  </ListItemAvatar>
                  <ListItemText
                    primary={plugin.name}
                    slotProps={{ primary: { style: { fontSize: "0.95rem" } } }}
                    secondary={
                      <>
                        <Typography
                          sx={{ display: "block", fontStyle: "italic" }}
                          component="span"
                          variant="body2"
                          color="text.primary"
                        >
                          {plugin.author}
                        </Typography>
                        <span>{plugin.description}</span>
                        <TaskStatusText task={task} />
                      </>
                    }
                    style={{ maxWidth: "525px" }}
                  />
                  <ListItemSecondaryAction sx={PLUGIN_ROW_ACTION_SX}>
                    <InstallButton
                      pluginName={plugin.name}
                      selectedTarget={selectedTarget}
                      isInstalled={isInstalled}
                      installedStatePending={installedStatePending}
                      task={task}
                      onInstall={onInstall}
                      ariaLabel="install"
                    />

                    <Button
                      component={Link}
                      target="_blank"
                      rel="noopener noreferrer"
                      to={plugin.homepage}
                      variant="text"
                      size="small"
                      color="primary"
                      aria-label="view homepage"
                      disabled={!plugin.homepage || plugin.homepage === "Unknown"}
                      endIcon={<OpenInNewIcon />}
                      sx={{ ml: "15px", textTransform: "none" }}
                    >
                      View
                    </Button>
                  </ListItemSecondaryAction>
                </ListItemStyled>
              );
            })}
          </List>
        )}
    </Box>
  );
}

function ListInstalledPlugins({ selectedTarget, installedPlugins, getTask, onUninstall }) {
  if (selectedTarget === BROADCAST_TARGET) {
    return (
      <Box sx={{ textAlign: "center", marginBottom: "50px", marginTop: "30px" }}>
        <Typography variant="body2" component="p" color="text.secondary">
          Choose a Pioreactor to view installed plugins.
        </Typography>
      </Box>
    );
  }

  if (installedPlugins.length === 0) {
    return (
      <Box sx={{ textAlign: "center", marginBottom: "50px", marginTop: "50px" }}>
        <Typography variant="body2" component="p" color="text.secondary">
          No installed plugins. Try installing one below, or read more about{" "}
          <a
            href="https://docs.pioreactor.com/user-guide/using-community-plugins"
            target="_blank"
            rel="noopener noreferrer"
          >
            Pioreactor plugins
          </a>
          .
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ mb: "15px", width: "100%" }}>
      <List>
        {installedPlugins.map((plugin) => {
          const homepage =
            typeof plugin.homepage === "string"
              ? plugin.homepage.replace(/^https?:\/\/127\.0\.0\.1(?::\d+)?/, "")
              : "";
          const uninstallName = plugin.source.startsWith("plugins/")
            ? plugin.source.slice(8, -3)
            : plugin.name;
          const task = getTask("uninstall", "installed", uninstallName);
          const isRunning = task?.status === "running";

          return (
            <ListItemStyled key={plugin.name}>
              <ListItemAvatar>
                <PluginAvatar name={plugin.name} source="installed" />
              </ListItemAvatar>
              <ListItemText
                primary={`${plugin.name} ${
                  plugin.version === "Unknown" ? "" : "(" + plugin.version + ")"
                }`}
                slotProps={{ primary: { style: { fontSize: "0.95rem" } } }}
                secondary={
                  <>
                    <Typography
                      sx={{ display: "block", fontStyle: "italic" }}
                      component="span"
                      variant="body2"
                      color="text.primary"
                    >
                      {plugin.author || "unknown author"}
                    </Typography>
                    <span>
                      {plugin.description === "Unknown"
                        ? "No description provided."
                        : plugin.description}
                    </span>
                    <TaskStatusText task={task} />
                  </>
                }
                style={{ maxWidth: "525px" }}
              />
              <ListItemSecondaryAction sx={PLUGIN_ROW_ACTION_SX}>
                <Button
                  onClick={() => onUninstall(uninstallName, plugin.name)}
                  variant="text"
                  size="small"
                  color="secondary"
                  aria-label={`uninstall ${plugin.name}`}
                  disabled={isRunning}
                  endIcon={isRunning ? <CircularProgress color="inherit" size={14} /> : <DeleteIcon />}
                  sx={{ ml: "3px", textTransform: "none" }}
                >
                  {isRunning ? "Uninstalling" : task?.status === "failed" ? "Retry" : "Uninstall"}
                </Button>
                <Button
                  component={Link}
                  target="_blank"
                  rel="noopener noreferrer"
                  to={homepage}
                  variant="text"
                  size="small"
                  color="primary"
                  aria-label="view homepage"
                  disabled={!homepage || homepage === "Unknown"}
                  endIcon={<OpenInNewIcon />}
                  sx={{ ml: "15px", textTransform: "none" }}
                >
                  View
                </Button>
              </ListItemSecondaryAction>
            </ListItemStyled>
          );
        })}
      </List>
    </Box>
  );
}

function ListUsbPlugins({
  selectedTarget,
  installedPlugins,
  installedStatePending,
  getTask,
  onInstall,
}) {
  const [usbName, setUsbName] = React.useState("");
  const [usbPlugins, setUsbPlugins] = React.useState([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let isActive = true;

    async function getUsbPlugins() {
      setIsLoading(true);
      setError("");

      try {
        const statusResponse = await fetch("/unit_api/usb");

        if (!statusResponse.ok) {
          throw new Error(`Unable to load USB status (HTTP ${statusResponse.status}).`);
        }

        const status = await statusResponse.json();
        const activeMount = status?.active_mount;

        if (!activeMount?.mountpoint || status.status !== "mounted") {
          if (isActive) {
            setUsbName("");
            setUsbPlugins([]);
          }
          return;
        }

        const artifactsResponse = await fetch("/unit_api/usb/artifacts");

        if (!artifactsResponse.ok) {
          throw new Error(`Unable to scan USB plugins (HTTP ${artifactsResponse.status}).`);
        }

        const artifacts = await artifactsResponse.json();

        if (!isActive) {
          return;
        }

        setUsbName(activeMount.display_name || "USB");
        setUsbPlugins(Array.isArray(artifacts?.plugins) ? artifacts.plugins : []);
      } catch (err) {
        if (!isActive) {
          return;
        }

        console.error("Error getting USB plugins:", err);
        setUsbName("");
        setUsbPlugins([]);
        setError(err instanceof Error ? err.message : "Failed to load USB plugins.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    getUsbPlugins();

    return () => {
      isActive = false;
    };
  }, []);

  if (isLoading) {
    return null;
  }

  if (error) {
    return (
      <Box sx={{ mb: "15px", width: "100%" }}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  if (!selectedTarget) {
    return null;
  }

  if (usbPlugins.length === 0) {
    return (
    <>
      <Typography variant="h6" component="h3">
        USB Device
      </Typography>
      <p> You can attach a USB with Pioreactor plugins to install them on your cluster.</p>
    </>
    )
  }

  return (
    <>
      <Typography variant="h6" component="h3">
        Plugins found on USB {usbName}
      </Typography>

      <Box sx={{ mb: "15px", width: "100%" }}>
        <List>
          {usbPlugins.map((plugin) => {
            const label = `${plugin.name}${plugin.version ? " (" + plugin.version + ")" : ""}`;
            const isInstalled = installedPlugins.includes(plugin.name);
            const task = getTask("install", "usb", plugin.name);

            return (
              <ListItemStyled key={plugin.path}>
                <ListItemAvatar>
                  <PluginAvatar name={plugin.name} source="usb" />
                </ListItemAvatar>
                <ListItemText
                  primary={label}
                  slotProps={{ primary: { style: { fontSize: "0.95rem" } } }}
                  secondary={
                    <>
                      <span>{plugin.path}</span>
                      <TaskStatusText task={task} />
                    </>
                  }
                  style={{ maxWidth: "525px" }}
                />
                <ListItemSecondaryAction sx={PLUGIN_ROW_ACTION_SX}>
                  <InstallButton
                    pluginName={plugin.name}
                    selectedTarget={selectedTarget}
                    isInstalled={isInstalled}
                    installedStatePending={installedStatePending}
                    task={task}
                    onInstall={() => onInstall(plugin)}
                    ariaLabel="install USB plugin"
                  />
                  <Button
                    variant="text"
                    size="small"
                    color="primary"
                    aria-label="view homepage"
                    disabled
                    endIcon={<OpenInNewIcon />}
                    sx={{ ml: "15px", textTransform: "none" }}
                  >
                    View
                  </Button>
                </ListItemSecondaryAction>
              </ListItemStyled>
            );
          })}
        </List>
      </Box>
    </>
  );
}

function PluginContainer() {
  const { pioreactorUnit } = useParams();
  const navigate = useNavigate();

  const [installedPlugins, setInstalledPlugins] = React.useState([]);
  const [isFetchComplete, setIsFetchComplete] = React.useState(false);
  const [selectedTarget, setSelectedTarget] = React.useState(pioreactorUnit || "");
  const [units, setUnits] = React.useState([]);
  const [installedPluginsFetchError, setInstalledPluginsFetchError] = React.useState("");
  const [unitsFetchError, setUnitsFetchError] = React.useState("");
  const [refreshInstalledPluginsCount, setRefreshInstalledPluginsCount] = React.useState(0);
  const [pluginTasks, setPluginTasks] = React.useState({});
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);
  const [snackbarMsg, setSnackbarMsg] = React.useState("");
  const latestPluginsRequestId = React.useRef(0);
  const selectedTargetRef = React.useRef(selectedTarget);
  const displayedSelectedTarget =
    selectedTarget === BROADCAST_TARGET || units.includes(selectedTarget) ? selectedTarget : "";
  const targetIsRealUnit = isRealUnitTarget(selectedTarget, units);
  const installedPluginNames =
    targetIsRealUnit && isFetchComplete && !installedPluginsFetchError
      ? installedPlugins.map((plugin) => plugin.name)
      : [];
  const installedStatePending = targetIsRealUnit && !isFetchComplete;

  React.useEffect(() => {
    selectedTargetRef.current = selectedTarget;
  }, [selectedTarget]);

  React.useEffect(() => {
    if (!targetIsRealUnit) {
      latestPluginsRequestId.current += 1;
      setInstalledPlugins([]);
      setInstalledPluginsFetchError("");
      setIsFetchComplete(true);
      return;
    }

    let isActive = true;
    const requestId = ++latestPluginsRequestId.current;

    async function getPluginsInstalled() {
      setIsFetchComplete(false);
      setInstalledPluginsFetchError("");

      try {
        const result = await fetchTaskResult(`/api/units/${selectedTarget}/plugins/installed`);
        const unitPlugins = result?.result?.[selectedTarget];

        if (!isActive || requestId !== latestPluginsRequestId.current) {
          return;
        }

        if (unitPlugins == null) {
          throw new Error("Could not reach this Pioreactor.");
        }

        if (!Array.isArray(unitPlugins)) {
          throw new Error("Installed plugins payload is not a list.");
        }

        setInstalledPlugins(unitPlugins);
      } catch (err) {
        if (!isActive || requestId !== latestPluginsRequestId.current) {
          return;
        }
        console.error("Error getting plugins installed:", err);
        setInstalledPlugins([]);
        setInstalledPluginsFetchError(
          err instanceof Error ? err.message : "Failed to load installed plugins.",
        );
      } finally {
        if (isActive && requestId === latestPluginsRequestId.current) {
          setIsFetchComplete(true);
        }
      }
    }

    getPluginsInstalled();

    return () => {
      isActive = false;
    };
  }, [selectedTarget, targetIsRealUnit, refreshInstalledPluginsCount]);

  React.useEffect(() => {
    let isActive = true;

    async function getUnits() {
      setUnitsFetchError("");

      try {
        const response = await fetch("/api/units");

        if (!response.ok) {
          throw new Error(`Unable to load units (HTTP ${response.status}).`);
        }

        const data = await response.json();
        const nextUnits = Array.isArray(data) ? data.map((unit) => unit.pioreactor_unit) : [];

        if (!isActive) {
          return;
        }

        setUnits(nextUnits);

        if (nextUnits.length === 0) {
          setSelectedTarget("");
          setInstalledPlugins([]);
          setIsFetchComplete(true);
          setUnitsFetchError("No units are available.");
          return;
        }

        setSelectedTarget((current) => {
          if (current === BROADCAST_TARGET && nextUnits.length > 1) {
            return current;
          }

          if (current && nextUnits.includes(current)) {
            return current;
          }

          if (pioreactorUnit === BROADCAST_TARGET && nextUnits.length > 1) {
            return BROADCAST_TARGET;
          }

          if (pioreactorUnit && nextUnits.includes(pioreactorUnit)) {
            return pioreactorUnit;
          }

          return nextUnits[0];
        });
      } catch (err) {
        if (!isActive) {
          return;
        }

        console.error("Error getting units:", err);
        setUnits([]);
        setSelectedTarget("");
        setInstalledPlugins([]);
        setIsFetchComplete(true);
        setUnitsFetchError(err instanceof Error ? err.message : "Failed to load units.");
      }
    }

    getUnits();

    return () => {
      isActive = false;
    };
  }, [pioreactorUnit]);

  const handleSnackbarClose = (_event, reason) => {
    if (reason === "clickaway") {
      return;
    }
    setSnackbarOpen(false);
  };

  const showSnackbar = React.useCallback((message) => {
    setSnackbarMsg(message);
    setSnackbarOpen(true);
  }, []);

  const refreshInstalledPluginsIfVisible = React.useCallback((target) => {
    const visibleTarget = selectedTargetRef.current;

    if (target === visibleTarget || (target === BROADCAST_TARGET && isRealUnitTarget(visibleTarget, units))) {
      setRefreshInstalledPluginsCount((count) => count + 1);
    }
  }, [units]);

  const runPluginTask = React.useCallback(
    async ({ action, source, pluginName, displayName, target, endpoint, fetchOptions }) => {
      const taskId = makeTaskKey(action, source, pluginName, target);
      const runningLabel = action === "uninstall" ? "Uninstalling" : "Installing";
      const visiblePluginName = displayName || pluginName;

      setPluginTasks((current) => ({
        ...current,
        [taskId]: {
          id: taskId,
          action,
          source,
          pluginName,
          displayName,
          target,
          status: "running",
          message: "",
        },
      }));
      showSnackbar(`${runningLabel} ${visiblePluginName} on ${getTargetLabel(target)}...`);

      try {
        await fetchTaskResult(endpoint, {
          fetchOptions,
          maxRetries: 240,
          delayMs: 500,
        });

        setPluginTasks((current) => ({
          ...current,
          [taskId]: {
            ...current[taskId],
            status: "succeeded",
            message: "",
          },
        }));
        showSnackbar(
          action === "uninstall"
            ? `Removed ${visiblePluginName} from ${getTargetLabel(target)}.`
            : `Installed ${visiblePluginName} on ${getTargetLabel(target)}.`,
        );
        refreshInstalledPluginsIfVisible(target);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Plugin task failed.";
        console.error("Plugin task failed:", err);
        setPluginTasks((current) => ({
          ...current,
          [taskId]: {
            ...current[taskId],
            status: "failed",
            message,
          },
        }));
        showSnackbar(message);
      }
    },
    [refreshInstalledPluginsIfVisible, showSnackbar],
  );

  const installCommunityPlugin = React.useCallback(
    (pluginName) => {
      if (!selectedTarget) {
        return;
      }

      runPluginTask({
        action: "install",
        source: "community",
        pluginName,
        target: selectedTarget,
        endpoint: `/api/units/${selectedTarget}/plugins/install`,
        fetchOptions: {
          method: "POST",
          body: JSON.stringify({ args: [pluginName] }),
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
        },
      });
    },
    [runPluginTask, selectedTarget],
  );

  const installUsbPlugin = React.useCallback(
    (plugin) => {
      if (!selectedTarget) {
        return;
      }

      runPluginTask({
        action: "install",
        source: "usb",
        pluginName: plugin.name,
        target: selectedTarget,
        endpoint: `/api/units/${selectedTarget}/plugins/install-from-leader-usb`,
        fetchOptions: {
          method: "POST",
          body: JSON.stringify({ filepath: plugin.path }),
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
        },
      });
    },
    [runPluginTask, selectedTarget],
  );

  const uninstallPlugin = React.useCallback(
    (pluginName, displayName) => {
      if (!selectedTarget || selectedTarget === BROADCAST_TARGET) {
        return;
      }

      runPluginTask({
        action: "uninstall",
        source: "installed",
        pluginName,
        displayName,
        target: selectedTarget,
        endpoint: `/api/units/${selectedTarget}/plugins/uninstall`,
        fetchOptions: {
          method: "POST",
          body: JSON.stringify({ args: [pluginName] }),
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
        },
      });
    },
    [runPluginTask, selectedTarget],
  );

  const getTask = React.useCallback(
    (action, source, pluginName) => pluginTasks[makeTaskKey(action, source, pluginName, selectedTarget)],
    [pluginTasks, selectedTarget],
  );

  const onSelectionChange = (e) => {
    const nextTarget = e.target.value;
    setSelectedTarget(nextTarget);
    navigate(`/plugins/${nextTarget}`);
  };

  return (
    <>
      <Card>
        <CardContent sx={{ p: 2 }}>
          <p>
            Discover, install, and manage Pioreactor plugins. These
            plugins can provide new functionalities for your Pioreactor (additional hardware may be
            necessary), or new automations to control dosing, temperature and LED tasks.
          </p>

          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2, flexWrap: "wrap" }}>
            <Typography variant="h5" component="h2" sx={{ fontWeight: "bold", my: 2}}>
              Manage plugins for

            <Select
              labelId="pluginTargetSelect"
              variant="standard"
              value={displayedSelectedTarget}
              onChange={onSelectionChange}
              disabled={units.length === 0}
              sx={{
                "& .MuiSelect-select": {
                  paddingY: 0,
                },
                fontWeight: 700,
                fontSize: "24px",
                letterSpacing: "0.15px",
                fontFamily: "inherit",
                lineHeight: "34.5px",
                marginLeft: "5px",
              }}
            >
              {units.map((unit) => (
                <MenuItem key={unit} value={unit}>
                  {unit}
                </MenuItem>
              ))}
              {units.length > 1 && (
                <MenuItem value={BROADCAST_TARGET}>
                  <PioreactorsIcon fontSize="small" sx={{ verticalAlign: "middle", mr: 0.5 }} />
                  All Pioreactors
                </MenuItem>
              )}
            </Select>
            </Typography>
          </Box>

          <Typography variant="h6" component="h3">
           Installed plugins
          </Typography>

          {!isFetchComplete && targetIsRealUnit && (
            <Box sx={{ textAlign: "center", marginBottom: "50px", marginTop: "50px" }}>
              <CircularProgress size={33} />
            </Box>
          )}

          {unitsFetchError && (
            <Box sx={{ textAlign: "center", marginBottom: "24px", marginTop: "16px" }}>
              <Typography variant="body2" component="p" color="text.secondary">
                {unitsFetchError}
              </Typography>
            </Box>
          )}

          {!unitsFetchError && isFetchComplete && installedPluginsFetchError && (
            <Box sx={{ textAlign: "center", marginBottom: "24px", marginTop: "16px" }}>
              <Typography variant="body2" component="p" color="error">
                {installedPluginsFetchError}
              </Typography>
            </Box>
          )}

          {!unitsFetchError && isFetchComplete && !installedPluginsFetchError && (
            <ListInstalledPlugins
              selectedTarget={selectedTarget}
              installedPlugins={installedPlugins}
              getTask={getTask}
              onUninstall={uninstallPlugin}
            />
          )}

          <ListUsbPlugins
            selectedTarget={selectedTarget}
            installedPlugins={installedPluginNames}
            installedStatePending={installedStatePending}
            getTask={getTask}
            onInstall={installUsbPlugin}
          />

          <Typography variant="h6" component="h3">
            Suggested plugins from the community
          </Typography>

          <ListSuggestedPlugins
            selectedTarget={selectedTarget}
            installedPlugins={installedPluginNames}
            installedStatePending={installedStatePending}
            getTask={getTask}
            onInstall={installCommunityPlugin}
          />
        </CardContent>
      </Card>
      <p style={{ textAlign: "center", marginTop: "30px" }}>
        Learn more about Pioreactor{" "}
        <a
          href="https://docs.pioreactor.com/user-guide/using-community-plugins"
          target="_blank"
          rel="noopener noreferrer"
        >
          plugins
        </a>
        .
      </p>
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={7000}
        key="snackbar-plugins"
      />
    </>
  );
}

function Plugins(props) {
  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);
  return (
    <Grid container spacing={2}>
      <Grid
        size={{
          md: 12,
          xs: 12,
        }}
      >
        <PageHeader />
        <PluginContainer />
      </Grid>
    </Grid>
  );
}

export default Plugins;
