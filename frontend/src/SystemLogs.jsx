import { useState, useEffect, Fragment } from 'react';

import Select from '@mui/material/Select';
import Grid from "@mui/material/Grid";
import MenuItem from "@mui/material/MenuItem";
import { useNavigate, useParams, useLocation } from 'react-router';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import PaginatedLogsTable from "./components/PaginatedLogsTable";
import PioreactorsIcon from './components/PioreactorsIcon';

function SystemLogs(props) {

  const location = useLocation();
  const {pioreactorUnit} = useParams();
  const [logLevel, setLogLevel] = useState(() => {
    return localStorage.getItem("systemLogLevel") || "DEBUG";
  });
  const [units, setUnits] = useState([])
  const navigate = useNavigate();

  useEffect(() => {
    localStorage.setItem("systemLogLevel", logLevel);
  }, [logLevel]);


  useEffect(() => {
    document.title = props.title;
  }, [props.title])

  useEffect(() => {
    async function fetchUnits() {
      try {
        const response = await fetch(`/api/units`);
        if (response.ok) {
          const units = await response.json();
          setUnits(units.map(u => u.pioreactor_unit));
        } else {
          console.error('Failed to fetch units:', response.statusText);
        }
      } catch (error) {
        console.error('Error fetching units:', error);
      }
    };

      fetchUnits()
  }, [location])

  const onSelectionChange = (event) => {
    // go to the selected units /log/<unit> page

    if (event.target.value === "$broadcast"){
      navigate(`/system-logs/`);
    }
    else{
      navigate(`/system-logs/${event.target.value}`);
    }
  }


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
                <span style={{marginRight: "8px"}}> system logs for</span>
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
                  {units.map((unit) => (
                    <MenuItem key={unit} value={unit}>{unit}</MenuItem>
                  ))}
                  <MenuItem value="$broadcast"><PioreactorsIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 4px"}} />All Pioreactors</MenuItem>
                </Select>
              </Typography>
            </Box>
          </Grid>
          <Grid size={{ md: 12, lg: 5}}>

          </Grid>
          <Grid>
            <PaginatedLogsTable pioreactorUnit={pioreactorUnit} experiment={"$experiment"} logLevel={logLevel} />
          </Grid>

      </Grid>
    </Fragment>
  );
}
export default SystemLogs;
