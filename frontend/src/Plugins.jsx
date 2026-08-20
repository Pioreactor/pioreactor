import Avatar from "boring-avatars";
import React from "react";
import UnderlineSpan from "./components/UnderlineSpan";

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
import { fetchTaskResult, getUnitTaskResult } from "./utils/tasks";
import { styled } from "@mui/material/styles";
import PioreactorsIcon from "./components/PioreactorsIcon";

const BROADCAST_TARGET = "$broadcast";
const PLUGIN_ROW_CONTENT_INSET = "2%";
const PLUGIN_ROW_ACTION_SX = {
  display: { xs: "contents", md: "block" },
  right: { md: `calc(${PLUGIN_ROW_CONTENT_INSET} + 16px)` },
};
const textIcon = { verticalAlign: "middle", margin: "0px 3px" };

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

function PageHeader({ units, selectedTarget, onSelectionChange }) {
  return (
    <Box component="header" sx={{ mb: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap", mb: 1 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: "bold" }}>
          <Box component="span" sx={{ mr: 0.5 }}>Manage plugins for</Box>
          <Select
            variant="standard"
            value={selectedTarget}
            onChange={onSelectionChange}
            disabled={units.length === 0}
            inputProps={{ "aria-label": "Pioreactor" }}
            sx={{
              "& .MuiSelect-select": {
                paddingY: 0,
              },
              fontWeight: "bold",
              fontSize: "inherit",
              fontFamily: "inherit",
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

function pluginUnitTaskResultSucceeded(unitResult) {
  if (unitResult === true) {
    return true;
  }

  if (unitResult === false || unitResult === null || unitResult === undefined) {
    return false;
  }

  if (typeof unitResult !== "object" || Array.isArray(unitResult)) {
    return false;
  }

  if (unitResult.error || unitResult.status === "failed") {
    return false;
  }

  if (unitResult.ok === false) {
    return false;
  }

  if (Object.prototype.hasOwnProperty.call(unitResult, "value")) {
    return pluginUnitTaskResultSucceeded(unitResult.value);
  }

  if (Object.prototype.hasOwnProperty.call(unitResult, "success")) {
    return unitResult.success === true;
  }

  return true;
}

function assertPluginTaskResultSucceeded(taskPayload, failureMessage) {
  const result = taskPayload?.result;

  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error(`${failureMessage}.`);
  }

  const failedUnits = Object.entries(result)
    .filter(([_unit, unitResult]) => !pluginUnitTaskResultSucceeded(unitResult))
    .map(([unit]) => unit);

  if (failedUnits.length === 1) {
    throw new Error(`${failureMessage} on ${failedUnits[0]}.`);
  }

  if (failedUnits.length > 1) {
    throw new Error(`${failureMessage} on ${failedUnits.join(", ")}.`);
  }
}

function PluginAvatar({ name, source = "community" }) {
  const colors =
    source === "installed"
      ? ["#5332ca", "#94ccc1", "#d8535e", "#f0b250", "#e5e5e5"]
      : ["#5332ca", "#856edb", "#94ccc1", "#d8535e", "#f0b250", "#e5e5e5"];

  return <Avatar name={`${name}${source}`} size={40} colors={colors} variant="bauhaus" />;
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
      sx={{ ml: "3px",  minWidth: 92 }}
    >
      {isRunning && <CircularProgress color="inherit" size={14} sx={textIcon} />}
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
        <Box sx={{ textAlign: "center", mb: "24px", mt: "24px" }}>
          <CircularProgress size={24} />
        </Box>
      )}

      {!isSuggestedPluginsLoading && suggestedPluginsFetchError && (
        <Box sx={{ textAlign: "center", mb: "24px", mt: "24px" }}>
          <Typography variant="body2" component="p" color="error">
            {suggestedPluginsFetchError}
          </Typography>
        </Box>
      )}

      {!isSuggestedPluginsLoading &&
        !suggestedPluginsFetchError &&
        availablePlugins.length === 0 && (
          <Box sx={{ textAlign: "center", mb: "24px", mt: "24px" }}>
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
                          sx={{ display: "block", fontStyle: "italic", my: 0.5 }}
                          component="span"
                          variant="body2"
                          color="text.primary"
                        >
                          Author: {plugin.author} · Version: {plugin.latest_version_available}
                        </Typography>
                        <span>{plugin.description}</span>
                      </>
                    }
                    sx={{ maxWidth: "525px" }}
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

                    {plugin.homepage && plugin.homepage !== "Unknown" && (
                      <Button
                        component={Link}
                        target="_blank"
                        rel="noopener noreferrer"
                        to={plugin.homepage}
                        variant="text"
                        size="small"
                        color="primary"
                        aria-label="view homepage"
                        endIcon={<OpenInNewIcon />}
                        sx={{ ml: "15px" }}
                      >
                        View homepage
                      </Button>
                    )}
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
      <Box sx={{ textAlign: "center", mb: "50px", mt: "30px" }}>
        <Typography variant="body2" component="p" color="text.secondary">
          Choose a Pioreactor to view installed plugins.
        </Typography>
      </Box>
    );
  }

  if (installedPlugins.length === 0) {
    return (
      <Box sx={{ textAlign: "center", mb: "50px", mt: "50px" }}>
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
                primary={plugin.name}
                slotProps={{ primary: { style: { fontSize: "0.95rem" } } }}
                secondary={
                  <>
                    <Typography
                      sx={{ display: "block", fontStyle: "italic",  my: 0.5 }}
                      component="span"
                      variant="body2"
                      color="text.primary"
                    >
                      Author: {plugin.author || "unknown author"} · Version: {plugin.version}
                    </Typography>
                    <span>
                      {plugin.description === "Unknown"
                        ? "No description provided."
                        : plugin.description}
                    </span>
                  </>
                }
                sx={{ maxWidth: "525px" }}
              />
              <ListItemSecondaryAction sx={PLUGIN_ROW_ACTION_SX}>
                <Button
                  onClick={() => onUninstall(uninstallName, plugin.name)}
                  variant="text"
                  size="small"
                  color="secondary"
                  aria-label={`uninstall ${plugin.name}`}
                  disabled={isRunning}
                  sx={{ ml: "3px" }}
                >
                  {isRunning
                    ? <CircularProgress color="inherit" size={14} sx={textIcon} />
                    : <DeleteIcon fontSize="small" sx={textIcon} />}
                  {isRunning ? "Uninstalling" : task?.status === "failed" ? "Retry" : "Uninstall"}
                </Button>
                {homepage && homepage !== "Unknown" && (
                  <Button
                    component={Link}
                    target="_blank"
                    rel="noopener noreferrer"
                    to={homepage}
                    variant="text"
                    size="small"
                    color="primary"
                    aria-label="view homepage"
                    endIcon={<OpenInNewIcon />}
                    sx={{ ml: "15px" }}
                  >
                    View homepage
                  </Button>
                )}
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
      <Typography variant="h6" component="h2">
        USB Device
      </Typography>
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "10vh" }}>
        <p>
           You can attach a USB with Pioreactor plugins to install them on your cluster. Learn more about {" "}
          <a
            href="https://docs.pioreactor.com/user-guide/using-usb-drives#install-plugins-from-usb"
            target="_blank"
            rel="noopener noreferrer"
          >
           USB-sourced plugins
          </a>.
        </p>
      </Box>
    </>
    )
  }

  return (
    <>
      <Typography variant="h6" component="h2">
        Plugins found on USB device <UnderlineSpan title="Attached to leader">{usbName}</UnderlineSpan>
      </Typography>

      <Box sx={{ mb: "15px", width: "100%" }}>
        <List>
          {usbPlugins.map((plugin) => {
            const pluginMetadata =
              plugin.kind === "python_file"
                ? "Type: Python file"
                : `Version: ${plugin.version || "Unknown"}`;
            const isInstalled = installedPlugins.includes(plugin.name);
            const task = getTask("install", "usb", plugin.name);

            return (
              <ListItemStyled key={plugin.path}>
                <ListItemAvatar>
                  <PluginAvatar name={plugin.name} source="usb" />
                </ListItemAvatar>
                <ListItemText
                  primary={plugin.name}
                  slotProps={{ primary: { style: { fontSize: "0.95rem" } } }}
                  secondary={
                    <>
                      <Typography
                        sx={{ display: "block", fontStyle: "italic", my: 0.5 }}
                        component="span"
                        variant="body2"
                        color="text.primary"
                      >
                        {pluginMetadata}
                      </Typography>
                      <span>{plugin.path}</span>
                    </>
                  }
                  sx={{ maxWidth: "525px" }}
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
        const unitPlugins = getUnitTaskResult(result, selectedTarget, "Could not reach this Pioreactor.");

        if (!isActive || requestId !== latestPluginsRequestId.current) {
          return;
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
        const taskPayload = await fetchTaskResult(endpoint, {
          fetchOptions,
          maxRetries: 240,
          delayMs: 500,
        });
        assertPluginTaskResultSucceeded(
          taskPayload,
          `Could not ${action === "uninstall" ? "remove" : "install"} ${visiblePluginName}`,
        );

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
      <PageHeader
        units={units}
        selectedTarget={displayedSelectedTarget}
        onSelectionChange={onSelectionChange}
      />
      <Card>
        <CardContent sx={{ p: 2 }}>
          <p>
            Discover, install, and manage Pioreactor plugins. These
            plugins can provide new functionalities for your Pioreactor (additional hardware may be
            necessary), or new automations to control dosing, temperature and LED tasks.
          </p>

          <Typography variant="h6" component="h2">
           Installed plugins
          </Typography>

          {!isFetchComplete && targetIsRealUnit && (
            <Box sx={{ textAlign: "center", mb: "50px", mt: "50px" }}>
              <CircularProgress size={33} />
            </Box>
          )}

          {unitsFetchError && (
            <Box sx={{ textAlign: "center", mb: "24px", mt: "16px" }}>
              <Typography variant="body2" component="p" color="text.secondary">
                {unitsFetchError}
              </Typography>
            </Box>
          )}

          {!unitsFetchError && isFetchComplete && installedPluginsFetchError && (
            <Box sx={{ textAlign: "center", mb: "24px", mt: "16px" }}>
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

          <Typography variant="h6" component="h2">
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
      <Box component="p" sx={{ textAlign: "center", mt: "30px" }}>
        Learn more about Pioreactor{" "}
        <a
          href="https://docs.pioreactor.com/user-guide/using-community-plugins"
          target="_blank"
          rel="noopener noreferrer"
        >
          plugins
        </a>
        .
      </Box>
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
        <PluginContainer />
      </Grid>
    </Grid>
  );
}

export default Plugins;
