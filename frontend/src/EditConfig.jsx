import React, {useCallback, useEffect, useMemo, useRef, useState} from "react";

import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import FormControl from '@mui/material/FormControl';
import Button from '@mui/material/Button';
import FormLabel from '@mui/material/FormLabel';
import Box from '@mui/material/Box';
import MenuItem from '@mui/material/MenuItem';
import {Typography} from '@mui/material';
import Snackbar from './components/Snackbar';
import Select from '@mui/material/Select';
import SaveIcon from '@mui/icons-material/Save';
import Editor from 'react-simple-code-editor';
import { highlight, languages } from 'prismjs';
import Alert from "@mui/material/Alert";
import 'prismjs/components/prism-ini';

import dayjs from "dayjs";
import { useParams, useNavigate } from 'react-router';


const CURRENT_VERSION = "__current__";
const SHARED_TARGET = "shared";


function getTargetMetadata(target) {
  if (target === SHARED_TARGET) {
    return {
      fetchUrl: "/api/config/shared",
      saveUrl: "/api/config/shared",
      historyUrl: "/api/config/shared/history",
      successLabel: "shared cluster config",
    };
  }

  return {
    fetchUrl: `/api/config/units/${target}/specific`,
    saveUrl: `/api/config/units/${target}/specific`,
    historyUrl: `/api/config/units/${target}/specific/history`,
    successLabel: `${target} unit config`,
  };
}


function EditableCodeDiv() {
  const { pioreactorUnit } = useParams();
  const navigate = useNavigate();
  const selectedTarget = pioreactorUnit || SHARED_TARGET;

  const [state, setState] = useState({
    code: null,
    currentCode: "",
    openSnackbar: false,
    snackbarMsg: "",
    saving: false,
    historicalConfigs: [],
    selectedVersion: CURRENT_VERSION,
    errorMsg: "",
    isError: false,
    hasChangedSinceSave: false,
    availableTargets: [{ name: "Shared cluster config", value: SHARED_TARGET }],
  });

  const loadRequestId = useRef(0);
  const currentTargetRef = useRef(selectedTarget);

  useEffect(() => {
    currentTargetRef.current = selectedTarget;
  }, [selectedTarget]);

  const loadConfigAndHistory = useCallback(async (target) => {
    const requestId = ++loadRequestId.current;
    const { fetchUrl, historyUrl } = getTargetMetadata(target);

    try {
      const [configResponse, historyResponse] = await Promise.all([
        fetch(fetchUrl),
        fetch(historyUrl),
      ]);

      if (!configResponse.ok || !historyResponse.ok) {
        throw new Error("Failed to load config data.");
      }

      const [text, listOfHistoricalConfigs] = await Promise.all([
        configResponse.text(),
        historyResponse.json(),
      ]);

      if (requestId !== loadRequestId.current) {
        return;
      }

      setState(prev => ({
        ...prev,
        code: text,
        currentCode: text,
        historicalConfigs: listOfHistoricalConfigs,
        selectedVersion: CURRENT_VERSION,
        hasChangedSinceSave: false,
        isError: false,
        errorMsg: "",
      }));
    } catch (err) {
      if (requestId !== loadRequestId.current) {
        return;
      }
      setState(prev => ({
        ...prev,
        code: "",
        currentCode: "",
        historicalConfigs: [],
        selectedVersion: CURRENT_VERSION,
        errorMsg: "Failed to load config. Is the unit online?",
        isError: true,
      }));
      console.error("Failed to fetch config/history:", err);
    }
  }, []);

  const saveCurrentCode = async () => {
    const targetAtSave = selectedTarget;
    const { saveUrl, successLabel } = getTargetMetadata(targetAtSave);

    setState(prev => ({ ...prev, saving: true, isError: false }));

    try {
      const res = await fetch(saveUrl, {
        method: "PATCH",
        body: JSON.stringify({ code: state.code }),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });

      if (res.ok) {
        if (currentTargetRef.current === targetAtSave) {
          await loadConfigAndHistory(targetAtSave);
        }
        setState(prev => ({
          ...prev,
          snackbarMsg: `Success: ${successLabel} saved.`,
          openSnackbar: true,
          isError: false
        }));
        return;
      }

      const parsedJson = await res.json();
      setState(prev => ({
        ...prev,
        errorMsg: parsedJson.error || "Save failed.",
        isError: true,
        hasChangedSinceSave: true,
      }));
    } catch (err) {
      setState(prev => ({ ...prev, errorMsg: "Save failed. Please retry.", isError: true }));
      console.error("Error saving config:", err);
    } finally {
      setState(prev => ({ ...prev, saving: false }));
    }
  };

  useEffect(() => {
    loadConfigAndHistory(selectedTarget);
  }, [loadConfigAndHistory, selectedTarget]);

  useEffect(() => {
    let ignore = false;

    async function getUnits() {
      try {
        const response = await fetch("/api/units");
        const json = await response.json();

        if (ignore) {
          return;
        }

        const unitTargets = json
          .map((entry) => entry.pioreactor_unit)
          .sort()
          .map((unit) => ({ name: `${unit} unit config`, value: unit }));

        setState(prev => {
          const targets = [{ name: "Shared cluster config", value: SHARED_TARGET }, ...unitTargets];
          const hasSelectedTarget = targets.some((entry) => entry.value === selectedTarget);

          if (!hasSelectedTarget && selectedTarget !== SHARED_TARGET) {
            targets.push({ name: `${selectedTarget} unit config`, value: selectedTarget });
          }

          return {
            ...prev,
            availableTargets: targets,
          };
        });
      } catch (err) {
        console.error("Failed to fetch unit list:", err);
      }
    }

    getUnits();

    return () => {
      ignore = true;
    };
  }, [selectedTarget]);

  const onSelectionChange = (e) => {
    const target = e.target.value;
    setState(prev => ({
      ...prev,
      code: "Loading...",
      currentCode: "",
      hasChangedSinceSave: false,
      isError: false,
      errorMsg: "",
      selectedVersion: CURRENT_VERSION,
    }));

    if (target === SHARED_TARGET) {
      navigate("/config");
    } else {
      navigate(`/config/${target}`);
    }
  };

  const onSelectionHistoricalChange = (e) => {
    const version = e.target.value;

    if (version === CURRENT_VERSION) {
      setState(prev => ({
        ...prev,
        code: prev.currentCode,
        selectedVersion: CURRENT_VERSION,
        hasChangedSinceSave: false,
      }));
      return;
    }

    const configBlob = state.historicalConfigs.find((config) => config.timestamp === version);
    if (!configBlob) {
      return;
    }

    setState(prev => ({
      ...prev,
      code: configBlob.data,
      selectedVersion: version,
      hasChangedSinceSave: true,
    }));
  };

  const onTextChange = (code) => {
    setState(prev => ({ ...prev, code: code, hasChangedSinceSave: true }));
  };

  const handleSnackbarClose = () => {
    setState(prev => ({ ...prev, openSnackbar: false }));
  };

  const versionOptions = useMemo(() => {
    return [{ label: "Current", value: CURRENT_VERSION }, ...state.historicalConfigs.map((configBlob) => ({
      label: dayjs(configBlob.timestamp).format("MMM DD, YYYY [at] hh:mm a"),
      value: configBlob.timestamp,
    }))];
  }, [state.historicalConfigs]);

  const isCodeLoaded = state.code !== null && state.code !== "Loading...";
  const isHistoricalSelection = state.selectedVersion !== CURRENT_VERSION;
  const canSaveOrRevert = isCodeLoaded && (state.hasChangedSinceSave || isHistoricalSelection) && !state.saving;

  return (
    <React.Fragment>
      <div style={{ width: "100%", margin: "10px", display: "flex", justifyContent: "space-between" }}>
        <FormControl>
          <div>
            <FormLabel component="legend">Config target</FormLabel>
            <Select
              labelId="configTargetSelect"
              variant="standard"
              value={selectedTarget}
              onChange={onSelectionChange}
            >
              {state.availableTargets.map((target) => (
                <MenuItem key={target.value} value={target.value}>{target.name}</MenuItem>
              ))}
            </Select>
          </div>
        </FormControl>
        <FormControl style={{ marginRight: "20px" }}>
          <div>
            <FormLabel component="legend">Versions</FormLabel>
            <Select
              labelId="historicalConfigSelect"
              variant="standard"
              value={state.selectedVersion}
              displayEmpty={true}
              onChange={onSelectionHistoricalChange}
            >
              {versionOptions.map((version) => (
                <MenuItem key={version.value} value={version.value}>{version.label}</MenuItem>
              ))}
            </Select>
          </div>
        </FormControl>
      </div>

      <div style={{
        tabSize: "4ch",
        border: "1px solid #ccc",
        margin: "10px auto 10px auto",
        position: "relative",
        width: "98%",
        borderRadius: "4px",
        height: "360px",
        maxHeight: "360px",
        overflow: "auto",
        flex: 1
      }}>
        {(state.code !== null) &&
          <Editor
            value={state.code}
            onValueChange={onTextChange}
            highlight={(code) => highlight(code, languages.ini)}
            padding={10}
            style={{
              fontSize: "14px",
              fontFamily: 'monospace',
              backgroundColor: "hsla(0, 0%, 100%, .5)",
              borderRadius: "3px",
              minHeight: "100%"
            }}
          />
        }
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div>
          <Button
            sx={{ margin: "5px 12px 5px 12px", textTransform: 'none' }}
            color="primary"
            variant="contained"
            onClick={saveCurrentCode}
            disabled={!canSaveOrRevert}
            loading={state.saving}
            loadingPosition="end"
            endIcon={<SaveIcon />}
          >
            {state.selectedVersion === CURRENT_VERSION ? "Save" : "Revert"}
          </Button>
          <Box sx={{ ml: 1, my: 1 }}>{state.isError ? <Alert severity="error">{state.errorMsg}</Alert> : ""}</Box>
        </div>
      </div>
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={state.openSnackbar}
        onClose={handleSnackbarClose}
        message={state.snackbarMsg}
        autoHideDuration={2500}
        key={"edit-config-snackbar"}
      />
    </React.Fragment>
  );
}


function EditConfigContainer(){
  return(
    <React.Fragment>

      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2">
            <Box sx={{ fontWeight: "fontWeightBold" }}>
              Configuration
            </Box>
          </Typography>
        </Box>
      </Box>

      <Card >
        <CardContent sx={{p: 1}}>
          <EditableCodeDiv/>

        </CardContent>
      </Card>
      <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about Pioreactor  <a href="https://docs.pioreactor.com/user-guide/configuration" target="_blank" rel="noopener noreferrer">configuration</a>.</p>
    </React.Fragment>
)}


function EditConfig(props) {
    React.useEffect(() => {
      document.title = props.title;
    }, [props.title])
    return (
      <Grid container spacing={2} >
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
           <EditConfigContainer/>
        </Grid>
      </Grid>
    );
}

export default EditConfig;
