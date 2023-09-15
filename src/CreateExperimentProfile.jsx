import React from "react";

import FormControl from '@mui/material/FormControl';
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import { makeStyles } from '@mui/styles';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import SaveIcon from '@mui/icons-material/Save';
import { CodeFlaskReact } from "react-codeflask"
import TextField from '@mui/material/TextField';
import InputAdornment from '@mui/material/InputAdornment';
import { Link } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import Snackbar from '@mui/material/Snackbar';

const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px"
  },
  formControl: {
    margin: theme.spacing(2),
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
  caption: {
    marginLeft: "30px",
    maxWidth: "650px"
  },
  headerMenu: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: "5px",
    [theme.breakpoints.down('lg')]:{
      flexFlow: "nowrap",
      flexDirection: "column",
    }
  },
  headerButtons: {display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"},
  textIcon: {
    verticalAlign: "middle",
    margin: "0px 3px"
  },
}));


class EditExperimentProfilesContent extends React.Component {
  DEFAULT_CODE = `experiment_profile_name:

metadata:
  description:
  author:
`
  DEFAULT_FILENAME = ""

  constructor(props) {
    super(props);
    this.state = {
      code: props.code || this.DEFAULT_CODE,
      filename: props.filename || this.DEFAULT_FILENAME,
      openSnackbar: false,
      snackbarMsg: "",
      isChanged: false,
    }
    this.saveCurrentCode = this.saveCurrentCode.bind(this);
  }

  getCodeFlaskRef = (codeFlask) => {
    this.codeFlask = codeFlask
  }

  onTextChange = (code) => {
    this.setState({code: code, isChanged: true})
  }

  onFilenameChange = (e) => {
    this.setState({filename: e.target.value, isChanged: true})
  }

  handleSnackbarClose = () => {
    this.setState({openSnackbar: false});
  };

  saveCurrentCode() {
    if (this.state.filename === "") {
      this.setState({isError: true, errorMsg: "Filename can't be blank"})
      return
    }

    this.setState({saving: true, isError: false, isChanged: false})
    fetch("/api/contrib/experiment_profiles",{
        method: "POST",
        body: JSON.stringify({body :this.state.code, filename: this.state.filename + '.yaml'}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
    .then(res => {
      if (res.ok) {
        this.setState({saving: false})
        this.setState({openSnackbar: true});
        this.setState({snackbarMsg: `Experiment profile ${this.state.filename}.yaml saved.`});
      } else {
        res.json().then(parsedJson =>
          this.setState({errorMsg: parsedJson['msg'], isError: true, saving: false, isChanged: true})
        )
      }
    })
  }


  render() {
    return (
      <>
      <Grid container spacing={1}>
        <Grid item xs={6}>
          <div style={{width: "100%", margin: "10px", display: "flex", justifyContent:"space-between"}}>
            <FormControl>
            <TextField
              label="Filename"
              onChange={this.onFilenameChange}
              required
              value={this.state.filename}
              styles={{width: "200px"}}
              InputProps={{
                endAdornment: <InputAdornment position="end">.yaml</InputAdornment>,
              }
            }

            />
            </FormControl>
          </div>
        </Grid>
        <Grid item xs={3} />
        <Grid container xs={3} direction="column" alignItems="flex-end">
          <Grid item xs={12} />
        </Grid>

        <Grid item xs={12}>
            <div style={{letterSpacing: "0em", margin: "10px auto 10px auto", position: "relative", width: "98%", height: "280px", border: "1px solid #ccc"}}>
              <CodeFlaskReact
                code={this.state.code}
                onChange={this.onTextChange}
                editorRef={this.getCodeFlaskRef}
                language={"yaml"}
              />
            </div>
        </Grid>
        <div style={{display: "flex", justifyContent: "space-between"}}>
          <div>
            <Button
              variant="contained"
              color="primary"
              style={{marginLeft: "20px"}}
              onClick={this.saveCurrentCode}
              endIcon={ <SaveIcon /> }
              disabled={!this.state.isChanged}
            >
              Save
           </Button>
           <p style={{marginLeft: "20px"}}>{this.state.isError ? <Box color="error.main">{this.state.errorMsg}</Box>: ""}</p>
          </div>
        </div>
      </Grid>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={this.state.openSnackbar}
        onClose={this.handleSnackbarClose}
        message={this.state.snackbarMsg}
        autoHideDuration={4000}
        key={"create-profile-snackbar"}
      />
      </>
    );
  }
}


function ProfilesContainer(props){
  const classes = useStyles();

  return(
    <React.Fragment>
      <div>
        <div className={classes.headerMenu}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Create Experiment Profile
            </Box>
          </Typography>
          <div className={classes.headerButtons}>
            <Button to={`/experiment-profiles`} component={Link} style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary">
              <ArrowBackIcon fontSize="15" classes={{root: classes.textIcon}}/> Back
            </Button>
          </div>
        </div>
      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <EditExperimentProfilesContent />
          <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/experiment-profiles-schema" target="_blank" rel="noopener noreferrer">experiment profile schemas</a>.</p>
        </CardContent>
      </Card>
    </React.Fragment>
)}


function CreateNewProfile(props) {

    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <ProfilesContainer />
          </Grid>
        </Grid>
    )
}

export default CreateNewProfile;
