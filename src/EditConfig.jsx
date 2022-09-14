import React from "react";

import Grid from '@mui/material/Grid';
import { makeStyles } from '@mui/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import FormControl from '@mui/material/FormControl';
import Button from '@mui/material/Button';
import LoadingButton from '@mui/lab/LoadingButton';
import InputLabel from '@mui/material/InputLabel';
import Box from '@mui/material/Box';
import {Typography} from '@mui/material';
import Snackbar from '@mui/material/Snackbar';
import Select from '@mui/material/Select';
import SaveIcon from '@mui/icons-material/Save';
import { CodeFlaskReact } from "react-codeflask"


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
      code: "",
      openSnackbar: false,
      filename: "config.ini",
      snackbarMsg: "",
      saving: false,
      hasChangedSinceSave: true,
      availableConfigs: [
        {name: "shared config.ini", filename: "config.ini"},
      ]
    };
    this.saveCurrentCode = this.saveCurrentCode.bind(this);
    this.deleteConfig = this.deleteConfig.bind(this);
  }

  getConfig(filename) {
    fetch("/api/get_config/" + filename)
      .then(response => {
        return response.text();
      })
      .then(text => {
        this.setState({code: text});
      })
  }

  getListOfConfigFiles(filename) {
    fetch("/api/get_configs")
      .then(response => {
        return response.json();
      })
      .then(json => {
        this.setState(prevState => ({
          availableConfigs: [...prevState.availableConfigs, ...json.filter(e => (e !== 'config.ini')).map(e => ({name: e, filename: e}))]
        }));
      })
  }

  saveCurrentCode() {
    this.setState({saving: true})
    fetch('/api/save_new_config',{
        method: "POST",
        body: JSON.stringify({code :this.state.code, filename: this.state.filename}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
    .then(res => {
      if (res.ok) {
        this.setState({snackbarMsg: this.state.filename + " saved and synced.", hasChangedSinceSave: false, saving: false})
      } else {
        this.setState({snackbarMsg: "Hm. Something when wrong saving or syncing...", hasChangedSinceSave: true, saving: false})
      }
      this.setState({openSnackbar: true});
    })
  }

  deleteConfig(){
    fetch('/api/delete_config',{
        method: "POST",
        body: JSON.stringify({filename: this.state.filename}),
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
  }

  onSelectionChange = (e) => {
    this.setState({filename: e.target.value})
    this.getConfig(e.target.value)
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
        <div style={{maxWidth: "200px", margin: "10px"}}>
          <FormControl fullWidth>

            <InputLabel id="configSelect" variant="standard">Config file</InputLabel>
            <Select
              native
              labelId="configSelect"
              variant="standard"
              value={this.state.filename}
              onChange={this.onSelectionChange}
              inputProps={{
                name: 'config',
                id: 'config',
              }}
            >
              {this.state.availableConfigs.map((v) => {
                return <option key={v.filename} value={v.filename}>{v.name}</option>
                }
              )}
            </Select>
          </FormControl>

        </div>

        <div style={{letterSpacing: "0em", margin: "10px auto 10px auto", position: "relative", width: "98%", height: "280px", border: "1px solid #ccc"}}>
          <CodeFlaskReact
            code={this.state.code}
            onChange={this.onTextChange}
            editorRef={this.getCodeFlaskRef}
            language={"python"}
          />
        </div>
        <div style={{display: "flex", justifyContent: "space-between"}}>
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
            Save
          </LoadingButton>
          <Button
            style={{margin: "5px 10px 5px 10px"}}
            color="secondary"
            onClick={this.deleteConfig}
            disabled={(this.state.filename === "config.ini")}>
            Delete config file
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
          <p style={{textAlign: "center", marginTop: "30px"}}><span role="img" aria-labelledby="Note">💡</span> Learn more about Pioreactor  <a href="https://docs.pioreactor.com/user-guide/configuration" target="_blank" rel="noopener noreferrer">configuration</a>.</p>
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

