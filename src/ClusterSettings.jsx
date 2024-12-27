import React from "react";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

import CircularProgress from '@mui/material/CircularProgress';

import Grid from '@mui/material/Grid';
import FormControl from '@mui/material/FormControl';
import TextField from '@mui/material/TextField';
import Divider from '@mui/material/Divider';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import MenuItem from '@mui/material/MenuItem';
import {Typography} from '@mui/material';
import Select from '@mui/material/Select';
import Box from '@mui/material/Box';
import LoadingButton from "@mui/lab/LoadingButton";
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import { useTheme } from '@mui/material/styles';
import Chip from '@mui/material/Chip';
import { Accordion, AccordionSummary, AccordionDetails, Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import ManageInventoryMenu from './components/ManageInventoryMenu';

// Activate the UTC plugin
dayjs.extend(utc);


// Reuse the provided checkTaskCallback
export async function checkTaskCallback(callbackURL, maxRetries = 50, delayMs = 200) {
  if (maxRetries <= 0) {
    throw new Error('Max retries reached. Stopping.');
  }

  try {
    const response = await fetch(callbackURL);
    if (response.status === 200) {
      return await response.json();
    }
    // If not 200, wait, decrement retry count, try again
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return checkTaskCallback(callbackURL, maxRetries - 1, delayMs);
  } catch (err) {
    console.error('Error fetching callback:', err);
    // Wait, decrement retry count, try again
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return checkTaskCallback(callbackURL, maxRetries - 1, delayMs);
  }
}

function ClusterClockCard(){
  const [clockData, setClockData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [updatingClock, setUpdatingClock] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [timestampLocal, setTimestampLocal] = React.useState(dayjs().local().format('YYYY-MM-DD HH:mm:ss'));

  React.useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch('/api/units/$broadcast/system/utc_clock', {
          method: 'GET'
        });
        if (!response.ok) {
          throw new Error(`Broadcast request failed with status ${response.status}`);
        }
        const broadcastData = await response.json();


        // Poll for the final result using checkTaskCallback
        const finalResult = await checkTaskCallback(broadcastData.result_url_path);

        setClockData(finalResult.result);
      } catch (err) {
        setError(err.message);
        console.error(err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handlePostTimestamp() {
    setUpdatingClock(true)
    try {
      const response = await fetch('/api/system/utc_clock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timestamp: dayjs(timestampLocal, 'YYYY-MM-DD HH:mm:ss').utc().format() })
      });
      if (!response.ok) {
        throw new Error(`Request failed with status: ${response.status}`);
      }
      const broadcastData = await response.json();
      const finalResult = await checkTaskCallback(broadcastData.result_url_path);
      setUpdatingClock(false)
      // Optionally handle success, e.g., show a confirmation message
    } catch (err) {
      console.error('Error posting timestamp:', err);
    }
  }

  return (
    <Card>
      <CardContent sx={{ p: 2 }}>
        <Typography variant="h6" component="h3" gutterBottom>
          Clocks
        </Typography>

        {loading && (
          <Box sx={{textAlign: "center"}}>
            <CircularProgress size={33}/>
          </Box>
        )}

        {error && (
          <Typography variant="body1" color="error">
            {error}
          </Typography>
        )}

        {!loading && !error && clockData && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Unit</TableCell>
                <TableCell>Clock time (localtime)</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(clockData).map(([unitName, info]) => {
                return (
                  <TableRow key={unitName}>
                    <TableCell>{unitName}</TableCell>
                    <TableCell>{info?.clock_time ? dayjs.utc(info.clock_time, 'YYYY-MM-DD[T]HH:mm:ss.SSS[Z]').local().format('MMM D, YYYY HH:mm') : "No data"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}

        <Box sx={{ mt: 4 }}>
        <TextField
          size="small"
          variant="outlined"
          label="Timestamp (localtime)"
          value={timestampLocal}
          onChange={(e) => setTimestampLocal(e.target.value)}
        />
        <LoadingButton
          variant="text"
          loading={updatingClock}
          sx={{ ml: 2, textTransform: "none" }}
          onClick={handlePostTimestamp}
        >
          Update clock
        </LoadingButton>
      </Box>
      </CardContent>
    </Card>
  );
}

function ClusterSettingsContainer() {
  return (
    <React.Fragment>
      <Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Cluster settings
            </Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <ManageInventoryMenu/>
          </Box>
        </Box>
        <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />

      </Box>

      <Grid container spacing={2}>
        <Grid item xs={5} md={5}>
          <ClusterClockCard/>
        </Grid>
      </Grid>
    </React.Fragment>
  );
}

function ClusterSettings(props) {
  React.useEffect(() => {
    document.title = props.title;
  }, [props.title]);

  return (
    <Grid container spacing={2}>
      <Grid item md={12} xs={12}>
        <ClusterSettingsContainer/>
      </Grid>
    </Grid>
  );
}

export default ClusterSettings;
