import React from "react";

import Grid from '@mui/material/Grid';
import { makeStyles } from '@mui/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import FormControl from '@mui/material/FormControl';
import Button from '@mui/material/Button';
import LoadingButton from '@mui/lab/LoadingButton';
import FormLabel from '@mui/material/FormLabel';
import Box from '@mui/material/Box';
import MenuItem from '@mui/material/MenuItem';
import {Typography} from '@mui/material';
import Snackbar from '@mui/material/Snackbar';
import Select from '@mui/material/Select';
import SaveIcon from '@mui/icons-material/Save';
import { CodeFlaskReact } from "react-codeflask"
import moment from "moment";
import DeleteIcon from '@mui/icons-material/Delete';

const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px",
  },
  title: {
    fontSize: 14,
  },
  cardContent: {
    padding: "10px"
  },
  pos: {
    marginBottom: 0,
  },
}));

class EditableCodeDiv extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      code: "Loading...",
      openSnackbar: false,
      filename: "config.ini",
      snackbarMsg: "",
      saving: false,
      historicalConfigs: [{filename: "config.ini", data: "", timestamp: "2000-01-01"}],
      timestamp_ix: 0,
      errorMsg: "",
      isError: false,
      hasChangedSinceSave: true,
      availableConfigs: [
        {name: "shared config.ini", filename: "config.ini"},
      ]
    };
    this.saveCurrentCode = this.saveCurrentCode.bind(this);
    this.deleteConfig = this.deleteConfig.bind(this);
  }

  getConfig(filename) {
    fetch(`/api/configs/${filename}`)
      .then(response => {
        return response.text();
      })
      .then(text => {
        this.setState({code: text});
      })
  }

  getListOfConfigFiles() {
    fetch("/api/configs")
      .then(response => {
        return response.json();
      })
      .then(json => {
        this.setState(prevState => ({
          availableConfigs: [...prevState.availableConfigs, ...json.filter(e => (e !== 'config.ini')).map(e => ({name: e, filename: e}))]
        }));
      })
  }

  getHistoricalConfigFiles(filename) {
    fetch("/api/historical_configs/" + filename)
      .then(response => {
        return response.json();
      })
      .then(listOfHistoricalConfigs => {
        this.setState({
          historicalConfigs: listOfHistoricalConfigs,
          timestamp_ix: 0
        });
      })
  }

  saveCurrentCode() {
    this.setState({saving: true, isError: false})
    fetch(`/api/configs/${this.state.filename}`,{
        method: "PATCH",
        body: JSON.stringify({code :this.state.code, filename: this.state.filename}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
    .then(res => {
      if (res.ok) {
        this.setState({snackbarMsg: this.state.filename + " saved and synced.", hasChangedSinceSave: false, saving: false})
        this.setState({openSnackbar: true});
      } else {
        res.json().then(parsedJson =>
          this.setState({errorMsg: parsedJson['msg'], isError: true, hasChangedSinceSave: true, saving: false})
        )
      }
    })
  }

  deleteConfig(){
    fetch(`/api/configs/${this.state.filename}`,{
        method: "DELETE",
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
    .then(res => {
      if (res.ok) {
        this.setState({snackbarMsg: this.state.filename + " deleted."})
      } else {
        this.setState({snackbarMsg: "Hm. Something when wrong deleting..."})
      }
      this.setState({openSnackbar: true});
      setTimeout(function () {
        window.location.reload();
      }, 750);
    })
  }

  componentDidMount() {
    this.getConfig(this.state.filename)
    this.getListOfConfigFiles()
    this.getHistoricalConfigFiles(this.state.filename)
    this.setState({timestamp: this.state.historicalConfigs[0].timestamp})
  }

  onSelectionChange = (e) => {
    const filename = e.target.value
    this.setState({filename: filename})
    this.getConfig(filename)
    this.getHistoricalConfigFiles(filename)
  }

  onSelectionHistoricalChange = (e) => {
    const timestamp = e.target.value
    const ix = this.state.historicalConfigs.findIndex((c) => c.timestamp === timestamp)
    const configBlob = this.state.historicalConfigs[ix]
    this.setState({code: configBlob.data, timestamp_ix: ix})
  }

  getCodeFlaskRef = (codeFlask) => {
    this.codeFlask = codeFlask
  }

  onTextChange = (code) => {
    this.setState({code: code, hasChangedSinceSave: true})
  }

  handleSnackbarClose = () => {
    this.setState({openSnackbar: false});
  };

  render() {
    return (
      <React.Fragment>
        <div style={{width: "100%", margin: "10px", display: "flex", justifyContent:"space-between"}}>
          <FormControl>
            <div>
              <FormLabel component="legend">Config file</FormLabel>
              <Select
                labelId="configSelect"
                variant="standard"
                value={this.state.filename}
                onChange={this.onSelectionChange}
              >
                {this.state.availableConfigs.map((v) => {
                  return <MenuItem key={v.filename} value={v.filename}>{v.name}</MenuItem>
                  }
                )}
              </Select>
            </div>
          </FormControl>
          {this.state.historicalConfigs.length > 0 ? (
          <FormControl style={{marginRight: "20px"}}>
            <div>
              <FormLabel component="legend">Versions</FormLabel>
              <Select
                labelId="historicalConfigSelect"
                variant="standard"
                value={this.state.historicalConfigs.length > 0 ? this.state.historicalConfigs[this.state.timestamp_ix].timestamp : ""}
                displayEmpty={true}
                onChange={this.onSelectionHistoricalChange}
              >
                {this.state.historicalConfigs.map((v, i) => {
                  return <MenuItem key={v.timestamp} value={v.timestamp}>{i === 0 ? "Current" : moment(v.timestamp).format("MMM DD [at] hh:mm a") }</MenuItem>
                  }
                )}
              </Select>
            </div>
          </FormControl>
        ) : <div></div>}

        </div>

        <div style={{letterSpacing: "0em", margin: "10px auto 10px auto", position: "relative", width: "98%", height: "280px", border: "1px solid #ccc"}}>
          <CodeFlaskReact
            code={this.state.code}
            onChange={this.onTextChange}
            editorRef={this.getCodeFlaskRef}
            language={"html"}
          />
        </div>
        <div style={{display: "flex", justifyContent: "space-between"}}>
          <div>
            <LoadingButton
              style={{margin: "5px 12px 5px 12px"}}
              color="primary"
              variant="contained"
              onClick={this.saveCurrentCode}
              disabled={!this.state.hasChangedSinceSave}
              loading={this.state.saving}
              loadingPosition="end"
              endIcon={<SaveIcon />}
              >
              {this.state.timestamp_ix === 0 ? "Save" : "Revert"}
            </LoadingButton>
            <p style={{marginLeft: 12}}>{this.state.isError ? <Box color="error.main">{this.state.errorMsg}</Box>: ""}</p>
          </div>
          <Button
            style={{margin: "5px 10px 5px 10px", textTransform: "none"}}
            color="secondary"
            onClick={this.deleteConfig}
            disabled={(this.state.filename === "config.ini")}
            >
            <DeleteIcon fontSize="15" /> Delete config file
          </Button>
        </div>
        <Snackbar
          anchorOrigin={{vertical: "bottom", horizontal: "center"}}
          open={this.state.openSnackbar}
          onClose={this.handleSnackbarClose}
          message={this.state.snackbarMsg}
          autoHideDuration={2000}
          key={"edit-config-snackbar"}
        />
      </React.Fragment>
    )
  }
}




function EditConfigContainer(){
  const classes = useStyles();

  return(
    <React.Fragment>
      <div>
        <div>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Configuration
            </Box>
          </Typography>
        </div>
      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <EditableCodeDiv/>

          <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about Pioreactor  <a href="https://docs.pioreactor.com/user-guide/configuration" target="_blank" rel="noopener noreferrer">configuration</a>.</p>
        </CardContent>
      </Card>
    </React.Fragment>
)}


function EditConfig(props) {
    React.useEffect(() => {
      document.title = props.title;
    }, [props.title])
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
             <EditConfigContainer/>
          </Grid>
        </Grid>
    )
}

export default EditConfig;

