import React from "react";
import TextField from '@mui/material/TextField';
import Divider from '@mui/material/Divider';

import Grid from '@mui/material/Grid';
import FormControl from '@mui/material/FormControl';
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
import DownloadIcon from '@mui/icons-material/Download';
import { useTheme } from '@mui/material/styles';
import Chip from '@mui/material/Chip';
import { Accordion, AccordionSummary, AccordionDetails, Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';


const datasetDescription = {
    marginLeft: "30px",
    fontSize: 14,
    color: 'text.secondary',
}


function getStyles(value, values, theme) {
  return {
    fontWeight: values.includes(value)
      ? theme.typography.fontWeightMedium
      : theme.typography.fontWeightRegular,
  };
}

function MultipleSelectChip({availableValues, parentHandleChange}) {
  const theme = useTheme();
  const [values, setValues] = React.useState([]);

  const handleChange = (event) => {
    const {
      target: { value },
    } = event;
    if (value.includes("<All experiments>")){
      setValues(["<All experiments>"]);
      parentHandleChange(["<All experiments>"])
    }
    else {
      setValues(value);
      parentHandleChange(value)
    }
  };

  return (
    <div>
      <FormControl fullWidth variant="standard" component="fieldset" sx={{ maxWidth: 470 }}>
        <Typography variant="h6" gutterBottom >
          <Box fontWeight="fontWeightRegular">Experiments</Box>
        </Typography>
        <Select
          labelId="expSelect"
          variant="standard"
          multiple
          value={values}
          onChange={handleChange}
          renderValue={(selected) => (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {selected.map((value) => (
                <Chip icon=<PlayCircleOutlinedIcon/> key={value} label={value} />
              ))}
            </Box>
          )}
          MenuProps={{ PaperProps: {
          style: {
              maxHeight: 250,
            },
          }}}
        >
          {availableValues.map((value) => (
            <MenuItem
              key={value}
              value={value}
              style={getStyles(value, values, theme)}
            >
              <Checkbox checked={values.includes(value)} /> {value}
            </MenuItem>
          ))}

        </Select>
      </FormControl>
    </div>
  );
}


function ExperimentSelection(props) {

  const [experiments, setExperiments] = React.useState([])

  React.useEffect(() => {
    async function getData() {
      try {
        const response = await fetch("/api/experiments");
        const data = await response.json();
        const experimentNames = data.map((e) => e.experiment);

        // Ensure "<All experiments>" is always at the bottom
        setExperiments([...experimentNames, "<All experiments>"]);
      } catch (error) {
        console.error("Failed to fetch experiments:", error);
      }
    }

    getData();
  }, []);


  return (
    <Box sx={{ m: 1}}>
      <MultipleSelectChip availableValues={experiments} parentHandleChange={props.handleChange} />
    </Box>
  )
}

const PartitionBySelection = (props) => {
  return (
    <Box sx={{mt: 1}}>
      <FormControl component="fieldset" >
        <Box>
          <FormControlLabel
            control={<Checkbox checked={props.partitionByExperimentSelection} onChange={props.handleChange} name="partition_by_experiment" />}
            label="Partition output CSVs by Experiment"
          /><br/>
          <FormControlLabel
            control={<Checkbox checked={props.partitionByUnitSelection} onChange={props.handleChange} name="partition_by_unit" />}
            label="Partition output CSVs by Pioreactor"
          />
        </Box>
      </FormControl>
    </Box>
)}

const Dataset = ({ dataset, isSelected, handleChange }) => {
  const [previewData, setPreviewData] = React.useState([]);
  const [isLoading, setIsLoading] = React.useState(false);

  const handlePreview = async (e, expanded) => {
    if (!expanded){
      return
    }
    setIsLoading(true);
    try {
      const response = await fetch(`/api/contrib/exportable_datasets/${dataset.dataset_name}/preview`);
      const data = await response.json();
      setPreviewData(data);
    } catch (error) {
      console.error("Failed to fetch preview data:", error);
      setPreviewData([]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box
      key={dataset.dataset_name}
      sx={{
        ml: 1,
        mt: 2,
        p: 1.5,
        borderLeft: isSelected ? "4px solid #5331CA" : "4px solid #ddd",
        borderRadius: "4px",
        backgroundColor: isSelected ? "#5331ca14" : "white",
        transition: "background-color 0.15s, border 0.15s",
      }}
    >
      <FormControlLabel
        control={
          <Checkbox
            checked={isSelected}
            onChange={handleChange}
            name={dataset.dataset_name}
          />
        }
        label={
          <Typography
            variant="subtitle1"
            sx={{ fontWeight: isSelected ? "bold" : "normal" }}
          >
            {dataset.display_name}
          </Typography>
        }
      />
      {dataset.source !== "app" && (
        <Typography
          sx={{ marginLeft: "30px" }}
          variant="caption"
          display="block"
          gutterBottom
          color="textSecondary"
        >
          {`Provided by ${dataset.source}`}
        </Typography>
      )}
      <Typography sx={datasetDescription}>{dataset.description}</Typography>
      <Accordion
        square
        disableGutters
        elevation={0}
        sx={{
          '&::before': {
            display: 'none',
          },
          marginLeft: "20px",
          backgroundColor: isSelected ? "#f6f4fa" : "white",
          marginTop: "8px",
          maxWidth: "70vw",
          "&.Mui-expanded": {
            backgroundColor: isSelected ? "#f6f4fa" : "#f9f9f9",
            marginLeft: "20px",
            width: "70vw",
            overflow: "scroll",
            minHeight: 0,
          },
          "&.Mui-expanded:first-of-type": {
            marginTop: "8px",
          },
        }}
        onChange={handlePreview}
      >
        <AccordionSummary
          sx={{
            flexDirection: 'row-reverse',
            fontWeight: "bold",
            '&:hover': {
              backgroundColor: "#f3f3f3",
            },
          }}
        expandIcon={<ArrowDropDownIcon />}
        >
          <Typography>Preview</Typography>
        </AccordionSummary>
        <AccordionDetails
          sx={{
            padding: 2,
            borderTop: '1px solid rgba(0, 0, 0, .125)',
          }}
        >
          {isLoading ? (
            <Typography>Loading preview...</Typography>
          ) : previewData.length > 0 ? (
            <>
            <Table>
              <TableHead>
                <TableRow>
                  {Object.keys(previewData[0]).map((key) => (
                    <TableCell key={key} sx={{ maxWidth: 200, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {key}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {previewData.map((row, index) => (
                  <TableRow key={index}>
                    {Object.values(row).map((value, idx) => (
                      <TableCell key={idx} sx={{ maxWidth: 200, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {value}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Typography color="textSecondary" sx={{fontSize: 12, m:2, mt: 1, md: 0}}>(Random sample from all experiments and units)</Typography>
            </>
          ) : (
            <Typography>No preview data available.</Typography>
          )}
        </AccordionDetails>
      </Accordion>
    </Box>
  );
};

const Datasets = ({ datasets, selectedDatasets, handleChange, onSelectAll }) => {
  return (
    <Box sx={{ m: 1 }}>
      <FormControl component="fieldset">
        <Typography variant="h6" >
          <Box fontWeight="fontWeightRegular">Available datasets</Box>
        </Typography>
        <FormGroup>
          <FormControlLabel
            control={<Checkbox
              checked={datasets.length > 0 && selectedDatasets.length === datasets.length}
              onChange={onSelectAll}
              name="select_all"
              sx={{ml: 3, my: 1}}
            />}
            label={<Typography component="span" fontStyle="italic">
  Select all
</Typography>}
          />
          {datasets.map((dataset) => (
            <Dataset
              key={dataset.dataset_name}
              dataset={dataset}
              isSelected={selectedDatasets.includes(dataset.dataset_name)}
              handleChange={handleChange}
            />
          ))}
        </FormGroup>
      </FormControl>
    </Box>
  );
};


function ExportDataContainer() {
  const [isRunning, setIsRunning] = React.useState(false)
  const [errorMsg, setErrorMsg] = React.useState("")
  const [datasets, setDatasets] = React.useState([])

  const [state, setState] = React.useState({
    experimentSelection: [],
    partitionByUnitSelection: false,
    partitionByExperimentSelection: true,
    selectedDatasets: [],
    // ISO-8601 strings in UTC
    startTime: null,
    endTime: null,
    // enable time filter inputs
    useTimeFilter: false,
  });


  React.useEffect(() => {

    async function getDatasets() {
      try {
        const response = await fetch("/api/contrib/exportable_datasets");
        const data = await response.json();
        setDatasets(data);
      } catch (error) {
        console.error("Failed to fetch datasets:", error);
      }
    }
    getDatasets()
  }, [])


  const onSubmit =  async (event) => {
    event.preventDefault();

    if (state.selectedDatasets.length === 0) {
      setErrorMsg("At least one dataset must be selected.");
      return;
    }

    setIsRunning(true);
    setErrorMsg("");
    try {
      const res = await fetch('/api/contrib/exportable_datasets/export_datasets',{
          method: "POST",
          body: JSON.stringify({
            experiments: state.experimentSelection,
            partition_by_unit: state.partitionByUnitSelection,
            partition_by_experiment: state.partitionByExperimentSelection,
            datasets: state.selectedDatasets,
            start_time: state.startTime,
            end_time: state.endTime,
          }),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          },
      });
      const resJson = await res.json();
      var link = document.createElement("a");
      const filename = resJson['filename'].replace(/%/g, "%25")
      link.setAttribute('export', filename);
      link.href = "/exports/" + filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch(e) {
      setErrorMsg("Server error occurred. Check logs.")
      console.log(e)
    } finally {
      setIsRunning(false);
    }
  }

  const handleCheckboxChange = (event) => {
    const { name, checked } = event.target;

    setState((prevState) => ({
      ...prevState,
      selectedDatasets: checked
        ? [...new Set([...prevState.selectedDatasets, name])]
        : prevState.selectedDatasets.filter((item) => item !== name),
    }));
  };

  const handleSelectAll = (event) => {
    const { checked } = event.target;
    setState(prevState => ({
      ...prevState,
      selectedDatasets: checked ? datasets.map(d => d.dataset_name) : [],
    }));
  };


  function handleExperimentSelectionChange(experiments) {
    setState(prevState => ({
      ...prevState,
      experimentSelection: experiments
    }));
  };

  function handlePartitionByChange(event) {
    const stateKey = {
      partition_by_unit: "partitionByUnitSelection",
      partition_by_experiment: "partitionByExperimentSelection",
    }[event.target.name];

    if (!stateKey) return;

    setState(prevState => ({
      ...prevState,
      [stateKey]: event.target.checked
    }));
  };

  const errorFeedbackOrDefault = errorMsg ? <Box color="error.main">{errorMsg}</Box>: ""
  const selectedDatasetsCount = state.selectedDatasets.length;
  const experimentSelectionCount = state.experimentSelection.length;
  return (
    <React.Fragment>
      <Box>
        <Box sx={{display: "flex", justifyContent: "space-between", mb: 1}}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Export data
            </Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <LoadingButton
                type="submit"
                variant="contained"
                color="primary"
                loading={isRunning}
                loadingPosition="end"
                onClick={onSubmit}
                endIcon={<DownloadIcon />}
                disabled={(selectedDatasetsCount === 0) || (experimentSelectionCount === 0)}
                style={{textTransform: 'none'}}
              >
                Export { selectedDatasetsCount > 0 ?  selectedDatasetsCount : ""}
            </LoadingButton>
          </Box>
        </Box>
      <Divider sx={{marginTop: "0px", marginBottom: "15px"}} />
      </Box>
      <Card>
        <CardContent sx={{ p: 1 }}>
          <p style={{ marginLeft: 10 }}>{errorFeedbackOrDefault}</p>

          <form>
            <Grid container spacing={2}>
              <Grid
                size={{
                  xs: 6,
                  md: 6
                }}>
                <ExperimentSelection
                  experimentSelection={state.experimentSelection}
                  handleChange={handleExperimentSelectionChange}
                />
              </Grid>
              <Grid  size={{
                  xs: 1,
                  md: 1
                }}/>
              <Grid
                size={{
                  xs: 5,
                  md: 5
                }}>
                <Accordion square disableGutters elevation={0} sx={{ '&::before': { display: 'none' }, backgroundColor: 'transparent', boxShadow: 'none', margin: 0 }}>
                  <AccordionSummary
                    sx={{
                      flexDirection: 'row-reverse',
                    }}
                    expandIcon={<ArrowDropDownIcon />}
                  >
                    <Typography variant="h6">
                      <Box fontWeight="fontWeightRegular">Export options</Box>
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <PartitionBySelection
                      partitionByUnitSelection={state.partitionByUnitSelection}
                      partitionByExperimentSelection={state.partitionByExperimentSelection}
                      handleChange={handlePartitionByChange}
                    />
                    {/* Time range selectors */}
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={state.useTimeFilter}
                          onChange={(e) =>
                            setState((prev) => ({
                              ...prev,
                              useTimeFilter: e.target.checked,
                            }))
                          }
                          name="useTimeFilter"
                        />
                      }
                      label="Filter by time range"
                    />
                    <Box sx={{ display: 'flex', gap: 2, mt: 1, mb: 2 }}>
                      <TextField
                        label="Start time"
                        type="datetime-local"
                        size="small"
                        InputLabelProps={{ shrink: true }}
                        disabled={!state.useTimeFilter}
                        value={state.startTime || ''}
                        onChange={(e) =>
                          setState((prev) => ({ ...prev, startTime: e.target.value }))
                        }
                      />
                      <TextField
                        label="End time"
                        type="datetime-local"
                        size="small"
                        InputLabelProps={{ shrink: true }}
                        disabled={!state.useTimeFilter}
                        value={state.endTime || ''}
                        onChange={(e) =>
                          setState((prev) => ({ ...prev, endTime: e.target.value }))
                        }
                      />
                    </Box>
                  </AccordionDetails>
                </Accordion>
              </Grid>
              <Grid
                size={{
                  xs: 12,
                  md: 12
                }}>
                <Datasets
                  selectedDatasets={state.selectedDatasets}
                  handleChange={handleCheckboxChange}
                  onSelectAll={handleSelectAll}
                  datasets={datasets}
                />
              </Grid>

              <Grid size={0} />
            </Grid>
          </form>
        </CardContent>
      </Card>
      <Grid size={12}>
        <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/export-data" target="_blank" rel="noopener noreferrer">data exporting</a>.</p>
      </Grid>
    </React.Fragment>
  );
}


function ExportData(props) {
    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
      <Grid container spacing={2} >
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <ExportDataContainer/>
        </Grid>
      </Grid>
    );
}

export default ExportData;
