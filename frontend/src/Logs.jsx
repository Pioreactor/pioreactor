import { useState, useEffect, Fragment } from 'react';

import Select from '@mui/material/Select';
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import { Link, useNavigate, useParams, useLocation } from 'react-router';
import DownloadIcon from '@mui/icons-material/Download';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import PaginatedLogsTable from "./components/PaginatedLogsTable";
import {getRelabelMap} from "./utilities"
import { useExperiment } from './providers/ExperimentContext';
import ManageExperimentMenu from "./components/ManageExperimentMenu";
import RecordEventLogDialog from './components/RecordEventLogDialog';
import PioreactorsIcon from './components/PioreactorsIcon';

function Logs(props) {

  const location = useLocation();
  const {pioreactorUnit} = useParams();
  const {experimentMetadata} = useExperiment()
  const [relabelMap, setRelabelMap] = useState({})
  const [logLevel, setLogLevel] = useState(() => {
    // Load logLevel from localStorage or default to "INFO"
    return localStorage.getItem("logLevel") || "INFO";
  });
  const [assignedUnits, setAssignedUnits] = useState([])
  const navigate = useNavigate();

  useEffect(() => {
    localStorage.setItem("logLevel", logLevel);
  }, [logLevel]);


  useEffect(() => {
    document.title = props.title;
  }, [props.title])

  useEffect(() => {
    async function fetchWorkers(experiment) {
      try {
        const response = await fetch(`/api/experiments/${experiment}/historical_worker_assignments`);
        if (response.ok) {
          const units = await response.json();
          setAssignedUnits(units.map(u => u.pioreactor_unit));
        } else {
          console.error('Failed to fetch workers:', response.statusText);
        }
      } catch (error) {
        console.error('Error fetching workers:', error);
      }
    };

    if (experimentMetadata.experiment){
        getRelabelMap(setRelabelMap, experimentMetadata.experiment)
        fetchWorkers(experimentMetadata.experiment)
    }
  }, [experimentMetadata, location])

  const onSelectionChange = (event) => {
    // go to the selected units /log/<unit> page

    if (event.target.value === "$broadcast"){
      navigate(`/logs/`);
    }
    else{
      navigate(`/logs/${event.target.value}`);
    }
  }


  const handleSubmitDialog = async (newLog) => {
    try {
      const response = await fetch(`/api/workers/${newLog.pioreactor_unit}/experiments/${newLog.experiment}/logs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newLog),
      });
      if (!response.ok) {
        throw new Error('Failed to submit new log entry.');
      }
    } catch (error) {
      console.error('Error adding new log entry:', error);
    }
  };
  return (
    <Fragment>
      <Grid container spacing={2} >
        <Grid size={{md: 12, lg: 7}}>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
              <Typography variant="h5" component="h2" sx={{ fontWeight: "bold" }}>

                <Select
                  labelId="levelSelect"
                  variant="standard"
                  value={logLevel}
                  onChange={(e) => setLogLevel(e.target.value)}

                  sx={{
                    "& .MuiSelect-select": {
                      paddingY: 0,
                    },
                    mr: 1,
                    fontWeight: "bold", // Matches the title font weight
                    fontSize: "inherit", // Inherits the Typography's font size
                    fontFamily: "inherit", // Inherits the Typography's font family
                  }}
                >
                  <MenuItem value="NOTICE">− Only important </MenuItem>
                  <MenuItem value="INFO" >= Standard </MenuItem>
                  <MenuItem value="DEBUG">≡ Detailed </MenuItem>
                </Select>
                <span style={{marginRight: "8px"}}> event logs for</span>
                <Select
                  labelId="configSelect"
                  variant="standard"
                  value={pioreactorUnit ? pioreactorUnit : "$broadcast"}
                  onChange={onSelectionChange}

                  sx={{
                    "& .MuiSelect-select": {
                      paddingY: 0,
                    },
                    fontWeight: "bold", // Matches the title font weight
                    fontSize: "inherit", // Inherits the Typography's font size
                    fontFamily: "inherit", // Inherits the Typography's font family
                  }}
                >
                  {assignedUnits.map((unit) => (
                    <MenuItem key={unit} value={unit}>{unit}</MenuItem>
                  ))}
                  <MenuItem value="$broadcast"><PioreactorsIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 4px"}} />All assigned Pioreactors</MenuItem>
                </Select>
              </Typography>
            </Box>
          </Grid>
          <Grid size={{ md: 12, lg: 5}}>
            <Box sx={{display: "flex", justifyContent: "flex-end", flexFlow: "wrap"}}>
              <RecordEventLogDialog
                defaultPioreactor={pioreactorUnit || ''}
                defaultExperiment={experimentMetadata.experiment}
                availableUnits={assignedUnits}
                onSubmit={handleSubmitDialog}
              />
              <Button to={`/export-data`} component={Link} style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary">
                <DownloadIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 3px"}}/> Export logs
              </Button>
              <Divider orientation="vertical" flexItem variant="middle"/>
              <ManageExperimentMenu experiment={experimentMetadata.experiment}/>
            </Box>
          </Grid>
          <Grid size={{xs: 12}}>
            <PaginatedLogsTable pioreactorUnit={pioreactorUnit} experiment={experimentMetadata.experiment} relabelMap={relabelMap} logLevel={logLevel} />
          </Grid>

      </Grid>
    </Fragment>
  );
}
export default Logs;
