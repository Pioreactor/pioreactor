import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router";
import { useConfirm } from 'material-ui-confirm';
import { CircularProgress, Button, Typography, Box, Divider } from "@mui/material";
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import IconButton from '@mui/material/IconButton';
import { fetchTaskResult } from "./utilities";
import { readyGreen } from "./color";
import MuiLink from '@mui/material/Link';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import CodeIcon from '@mui/icons-material/Code';
import Grid from "@mui/material/Grid";

import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@mui/material";
import PioreactorIcon from "./components/PioreactorIcon";
import yaml from "js-yaml";
import dayjs from 'dayjs';
import Snackbar from '@mui/material/Snackbar';
import EstimatorIcon from './components/EstimatorIcon';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import Chip from '@mui/material/Chip';
import DoNotDisturbOnOutlinedIcon from '@mui/icons-material/DoNotDisturbOnOutlined';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';
import DisplaySourceCode from "./components/DisplaySourceCode";
import CloseIcon from '@mui/icons-material/Close';


function Delete({ pioreactorUnit, device, estimatorName }) {
  const navigate = useNavigate();
  const confirm = useConfirm();

  const deleteEstimator = async () => {
    try {
      await confirm({
        description: 'Deleting this estimator will remove it from disk. This is irreversible. Do you wish to continue?',
        title: `Delete estimator ${estimatorName}?`,
        confirmationText: "Confirm",
        confirmationButtonProps: { color: "primary", sx: { textTransform: 'none' } },
        cancellationButtonProps: { color: "secondary", sx: { textTransform: 'none' } },
      });

      const response = await fetch(`/api/workers/${pioreactorUnit}/estimators/${device}/${estimatorName}`, {
        method: "DELETE",
      });

      if (response.ok) {
        navigate(`/estimators/${pioreactorUnit}/${device}`, { replace: true });
      }
    } catch (err) {
      // confirmation rejected or request failed; no further action needed
    }
  };

  return (
    <Button style={{ textTransform: 'none', marginRight: "0px", float: "right" }} color="secondary" onClick={deleteEstimator}>
      <DeleteOutlineIcon fontSize="small" /> Delete
    </Button>
  );
}


function ViewYamlSource({ pioreactorUnit, device, estimatorName }) {
  const [open, setOpen] = useState(false);
  const [yamlText, setYamlText] = useState("");
  const [loading, setLoading] = useState(false);

  const openAndLoad = async () => {
    setOpen(true);
    setLoading(true);
    setYamlText("");
    try {
      const apiUrl = `/api/workers/${pioreactorUnit}/estimators/${device}/${estimatorName}`;
      const data = await fetchTaskResult(apiUrl);
      const estimator = data.result[pioreactorUnit];

      const yamlObj = {
        ...estimator,
      };
      delete yamlObj["is_active"];
      delete yamlObj["pioreactor_unit"];
      delete yamlObj["device"];

      const text = yaml.dump(yamlObj, { schema: yaml.JSON_SCHEMA });
      setYamlText(text);
    } catch (err) {
      console.error('Failed to load YAML', err);
      setYamlText('# Error loading YAML');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => setOpen(false);

  return (
    <>
      <Button
        style={{ textTransform: 'none', marginRight: '12px', float: 'right' }}
        onClick={openAndLoad}
      >
        <CodeIcon fontSize="small" sx={{ verticalAlign: "middle", margin: "0px 3px" }} />
        View YAML
      </Button>
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle>
          YAML description for estimator {estimatorName}
          <IconButton
            aria-label="close"
            onClick={handleClose}
            sx={{
              position: 'absolute',
              right: 8,
              top: 8,
              color: (theme) => theme.palette.grey[500],
            }}
            size="large">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          {loading ? (
            <Box textAlign="center" mt={2}><CircularProgress size={20} /></Box>
          ) : (
            <DisplaySourceCode sourceCode={yamlText} />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} sx={{ textTransform: 'none' }} autoFocus>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}


function SingleEstimatorPage(props) {
  const { pioreactorUnit, device, estimatorName } = useParams();
  const [estimator, setEstimator] = useState(null);
  const [loading, setLoading] = useState(true);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  const fetchSingleEstimator = async () => {
    setLoading(true);
    const apiUrl = `/api/workers/${pioreactorUnit}/estimators/${device}/${estimatorName}`;
    try {
      const data = await fetchTaskResult(apiUrl);
      setEstimator(data.result[pioreactorUnit]);
    } catch (err) {
      console.error("Failed to fetch estimator:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSingleEstimator();
  }, [pioreactorUnit, device, estimatorName]);

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false);
  };

  const showSnackbar = (message) => {
    setSnackbarMessage(message);
    setSnackbarOpen(true);
  };

  const handleSetActive = async () => {
    const apiUrl = `/api/workers/${pioreactorUnit}/active_estimators/${device}/${estimatorName}`;
    try {
      const response = await fetch(apiUrl, { method: "PATCH" });
      if (!response.ok) {
        throw new Error("Failed to activate estimator");
      }
      showSnackbar("Estimator set as Active");
      await fetchSingleEstimator();
    } catch (err) {
      console.error("Error setting active estimator:", err);
    }
  };

  const handleRemoveActive = async () => {
    const apiUrl = `/api/workers/${pioreactorUnit}/active_estimators/${device}`;
    try {
      const response = await fetch(apiUrl, { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Failed to remove active estimator");
      }
      showSnackbar("Estimator is no longer Active");
      await fetchSingleEstimator();
    } catch (err) {
      console.error("Error removing active estimator:", err);
    }
  };

  const isActive = estimator?.is_active ?? false;

  return (
    <>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h1">
            <Box sx={{ display: "inline" }}>
              <Button to={`/estimators`} component={Link} sx={{ textTransform: 'none' }}>
                <ArrowBackIcon sx={{ verticalAlign: "middle", mr: 0.5 }} fontSize="small" /> All estimators
              </Button>
            </Box>
          </Typography>

          <Box sx={{ display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap", alignItems: "center" }}>
            <ViewYamlSource pioreactorUnit={pioreactorUnit} device={device} estimatorName={estimatorName} />
            <Delete pioreactorUnit={pioreactorUnit} device={device} estimatorName={estimatorName} />
            <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />
            <Button
              startIcon={isActive ? <DoNotDisturbOnOutlinedIcon /> : <CheckCircleOutlineOutlinedIcon />}
              variant={isActive ? "text" : "contained"}
              color="primary"
              disabled={loading || !estimator}
              onClick={isActive ? handleRemoveActive : handleSetActive}
              sx={{ textTransform: "none", ml: 1, mr: 1 }}
            >
              {isActive ? "Set inactive" : "Set active"}
            </Button>
          </Box>
        </Box>
      </Box>
      <SingleEstimatorPageCard
        pioreactorUnit={pioreactorUnit}
        device={device}
        estimatorName={estimatorName}
        estimator={estimator}
        loading={loading}
      />

      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={snackbarOpen}
        onClose={handleSnackbarClose}
        message={snackbarMessage}
        autoHideDuration={7000}
        resumeHideDuration={2000}
        key={"snackbar" + pioreactorUnit + device + estimatorName}
      />
    </>
  );
}


function SingleEstimatorPageCard({ pioreactorUnit, device, estimatorName, estimator, loading }) {
  if (loading) {
    return (
      <Box textAlign="center" mt={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (!estimator) {
    return (
      <Box sx={{ textAlign: "center", mb: '50px', mt: "50px" }}>
        <Typography variant="body2" component="p" color="textSecondary">
          Unable to find estimator data.
        </Typography>
      </Box>
    );
  }

  const {
    estimator_type,
    created_at,
    recorded_data,
    is_active,
  } = estimator;

  const recordedDataText = recorded_data ? yaml.dump(recorded_data, { schema: yaml.JSON_SCHEMA }) : null;

  return (
    <Grid container spacing={0}>
      <Grid size={12} sx={{ mb: 2 }}>
        <Card>
          <CardContent sx={{ p: 2 }}>
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="h6" component="h2">
                  Estimator: {estimatorName}
                </Typography>
                {is_active && (
                  <Chip
                    size="small"
                    label={"Active"}
                    icon={<CheckCircleOutlineOutlinedIcon />}
                    sx={{
                      color: readyGreen,
                      border: "none",
                      backgroundColor: "transparent",
                      "& .MuiChip-icon": { color: readyGreen },
                    }}
                  />
                )}
              </Box>
              <Typography variant="subtitle2" color="text.secondary">
                <MuiLink
                  component={Link}
                  to={`/estimators/${pioreactorUnit}`}
                  color="inherit"
                  underline="hover"
                  sx={{ fontWeight: 500 }}
                >
                  {pioreactorUnit}
                </MuiLink>
                {" / "}
                <MuiLink
                  component={Link}
                  to={`/estimators/${pioreactorUnit}/${device}`}
                  color="inherit"
                  underline="hover"
                  sx={{ fontWeight: 500 }}
                >
                  {device}
                </MuiLink>
              </Typography>
            </Box>

            <Box sx={{ px: 5, mt: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="h6">Estimator data</Typography>
              </Box>
              <Table size="small">
                <TableBody>
                  <TableRow>
                    <TableCell><strong>Estimator name</strong></TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        icon={<EstimatorIcon />}
                        label={estimatorName}
                        data-estimator-name={estimatorName}
                      />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Pioreactor</strong></TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        icon={<PioreactorIcon />}
                        label={pioreactorUnit}
                        clickable
                        component={Link}
                        to={`/estimators/${pioreactorUnit}`}
                        data-pioreactor-unit={pioreactorUnit}
                      />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Created at</strong></TableCell>
                    <TableCell>{dayjs(created_at).format('MMMM D, YYYY, h:mm a')}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Active</strong></TableCell>
                    <TableCell>
                      {is_active && (
                        <Chip
                          size="small"
                          label={"Active"}
                          icon={<CheckCircleOutlineOutlinedIcon />}
                          sx={{
                            color: readyGreen,
                            border: "none",
                            backgroundColor: "transparent",
                            "& .MuiChip-icon": { color: readyGreen },
                          }}
                        />
                      )}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Device</strong></TableCell>
                    <TableCell>{device}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Estimator type</strong></TableCell>
                    <TableCell>{estimator_type}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </Box>

            {recordedDataText && (
              <Box sx={{ px: 5, mt: 5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="h6">Recorded data</Typography>
                </Box>
                <DisplaySourceCode sourceCode={recordedDataText} />
              </Box>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}


export default SingleEstimatorPage;
