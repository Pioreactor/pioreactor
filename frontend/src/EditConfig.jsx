import React, {useCallback, useEffect, useRef, useState} from "react";

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


function EditableCodeDiv() {
  const [state, setState] = useState({
    code: null,
    openSnackbar: false,
    filename: "config.ini",
    snackbarMsg: "",
    saving: false,
    historicalConfigs: [{ filename: "config.ini", data: "", timestamp: "2000-01-01" }],
    timestamp_ix: 0,
    errorMsg: "",
    isError: false,
    hasChangedSinceSave: false,
    availableConfigs: [{ name: "shared config.ini", filename: "config.ini" }]
  });

  const loadRequestId = useRef(0);
  const currentFilenameRef = useRef(state.filename);

  useEffect(() => {
    currentFilenameRef.current = state.filename;
  }, [state.filename]);

  const loadConfigAndHistory = useCallback(async (filename) => {
    const requestId = ++loadRequestId.current;
    try {
      const [configResponse, historyResponse] = await Promise.all([
        fetch(`/api/config/files/${filename}`),
        fetch(`/api/config/files/${filename}/history`)
      ]);

      if (!configResponse.ok || !historyResponse.ok) {
        throw new Error("Failed to load config data.");
      }

      const [text, listOfHistoricalConfigs] = await Promise.all([
        configResponse.text(),
        historyResponse.json()
      ]);

      if (requestId !== loadRequestId.current) {
        return;
      }

      setState(prev => ({
        ...prev,
        code: text,
        historicalConfigs: listOfHistoricalConfigs,
        timestamp_ix: 0,
        hasChangedSinceSave: false
      }));
    } catch (err) {
      if (requestId !== loadRequestId.current) {
        return;
      }
      setState(prev => ({ ...prev, code: "# Error loading config" }));
      console.error("Failed to fetch config/history:", err);
    }
  }, []);

  const saveCurrentCode = async () => {
    const filenameAtSave = state.filename;
    setState(prev => ({ ...prev, saving: true, isError: false }));
    try {
      const res = await fetch(`/api/config/files/${filenameAtSave}`, {
        method: "PATCH",
        body: JSON.stringify({ code: state.code, filename: filenameAtSave }),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });

      if (res.ok) {
        if (currentFilenameRef.current === filenameAtSave) {
          await loadConfigAndHistory(filenameAtSave);
        }
        setState(prev => ({
          ...prev,
          snackbarMsg: `Success: ${filenameAtSave} saved and synced.`,
          openSnackbar: true,
          isError: false
        }));
        return;
      }

      const parsedJson = await res.json();
      setState(prev => ({ ...prev, errorMsg: parsedJson.error, isError: true, hasChangedSinceSave: true }));
    } catch (err) {
      setState(prev => ({ ...prev, errorMsg: "Save failed. Please retry.", isError: true }));
      console.error("Error saving config:", err);
    } finally {
      setState(prev => ({ ...prev, saving: false }));
    }
  };

  useEffect(() => {
    loadConfigAndHistory(state.filename);
  }, [state.filename, loadConfigAndHistory]);

  useEffect(() => {
    // what's up with the ignore? https://react.dev/learn/synchronizing-with-effects#fetching-data
    let ignore = false;

    async function getConfigs() {
      try {
        const response = await fetch("/api/config/files");
        const json = await response.json();
        if (ignore){
          return
        }
        setState(prev => {
          const existing = new Set(prev.availableConfigs.map((config) => config.filename));
          const newEntries = json
            .filter((e) => e !== 'config.ini')
            .map((e) => ({ name: e, filename: e }))
            .filter((entry) => !existing.has(entry.filename));

          if (newEntries.length === 0) {
            return prev;
          }

          return {
            ...prev,
            availableConfigs: [...prev.availableConfigs, ...newEntries]
          };
        })
      } catch (err) {
        console.error("Failed to fetch config list:", err);
      }
    }

    getConfigs()

    return () => {
      ignore = true;
    };
  }, []);

  // URL <-> selection sync
  const { pioreactorUnit } = useParams();
  const navigate = useNavigate();

  useEffect(() => {
    const desired = pioreactorUnit ? `config_${pioreactorUnit}.ini` : "config.ini";
    if (state.filename !== desired) {
      setState(prev => ({ ...prev, filename: desired, code: "Loading..." }));
    }
    if (pioreactorUnit) {
      const exists = state.availableConfigs.some((v) => v.filename === desired);
      if (!exists) {
        setState(prev => ({ ...prev, availableConfigs: [...prev.availableConfigs, {name: desired, filename: desired}] }));
      }
    }
  }, [pioreactorUnit, state.availableConfigs, state.filename]);

  const onSelectionChange = (e) => {
    const filename = e.target.value;
    setState(prev => ({ ...prev, filename: filename, code: "Loading...", hasChangedSinceSave: false }));
    if (filename === "config.ini") {
      navigate(`/config`);
    } else if (filename.startsWith("config_") && filename.endsWith(".ini")) {
      const unit = filename.replace(/^config_/, '').replace(/\.ini$/, '');
      navigate(`/config/${unit}`);
    }
  };

  const onSelectionHistoricalChange = (e) => {
    const timestamp = e.target.value;
    const ix = state.historicalConfigs.findIndex((c) => c.timestamp === timestamp);
    if (ix < 0) {
      return;
    }
    const configBlob = state.historicalConfigs[ix];
    setState(prev => ({ ...prev, code: configBlob.data, timestamp_ix: ix, hasChangedSinceSave: ix !== 0 }));
  };

  const onTextChange = (code) => {
    setState(prev => ({ ...prev, code: code, hasChangedSinceSave: true }));
  };

  const handleSnackbarClose = () => {
    setState(prev => ({ ...prev, openSnackbar: false }));
  };

  const selectedTimestamp = state.historicalConfigs[state.timestamp_ix]?.timestamp || "";
  const isCodeLoaded = state.code !== null && state.code !== "Loading...";
  const isHistoricalSelection = state.timestamp_ix !== 0;
  const canSaveOrRevert = isCodeLoaded && (state.hasChangedSinceSave || isHistoricalSelection) && !state.saving;

  return (
    <React.Fragment>
      <div style={{ width: "100%", margin: "10px", display: "flex", justifyContent: "space-between" }}>
        <FormControl>
          <div>
            <FormLabel component="legend">Config file</FormLabel>
            <Select
              labelId="configSelect"
              variant="standard"
              value={state.filename}
              onChange={onSelectionChange}
            >
              {state.availableConfigs.map((v) => (
                <MenuItem key={v.filename} value={v.filename}>{v.name}</MenuItem>
              ))}
            </Select>
          </div>
        </FormControl>
        {state.historicalConfigs.length > 0 ? (
          <FormControl style={{ marginRight: "20px" }}>
            <div>
              <FormLabel component="legend">Versions</FormLabel>
              <Select
                labelId="historicalConfigSelect"
                variant="standard"
                value={selectedTimestamp}
                displayEmpty={true}
                onChange={onSelectionHistoricalChange}
              >
                {state.historicalConfigs.map((v, i) => (
                  <MenuItem key={v.timestamp} value={v.timestamp}>{i === 0 ? "Current" : dayjs(v.timestamp).format("MMM DD, YYYY [at] hh:mm a")}</MenuItem>
                ))}
              </Select>
            </div>
          </FormControl>
        ) : <div></div>}

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
            {state.timestamp_ix === 0 ? "Save" : "Revert"}
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
            <Box fontWeight="fontWeightBold">
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
