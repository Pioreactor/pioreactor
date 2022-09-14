import React from 'react'
import moment from "moment";
import Card from '@mui/material/Card';
import {makeStyles} from '@mui/styles';
import CardContent from '@mui/material/Card';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import OutlinedInput from '@mui/material/OutlinedInput';
import InputLabel from '@mui/material/InputLabel';
import Divider from '@mui/material/Divider';
import Button from '@mui/material/Button';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import TimelapseIcon from '@mui/icons-material/Timelapse';
import GetAppIcon from '@mui/icons-material/GetApp';
import ClearIcon from '@mui/icons-material/Clear';
import AddIcon from '@mui/icons-material/Add';
import { useConfirm } from 'material-ui-confirm';



const useStyles = makeStyles((theme) => ({
  title: {
    fontSize: 14,
  },
  cardContent: {
    padding: "10px"
  },
  pos: {
    marginBottom: 0,
  },
  textIcon: {
    fontSize: 15,
    verticalAlign: "middle",
    margin: "0px 3px"
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
  headerButtons: {display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}
}));



class EditableDescription extends React.Component {
  constructor(props) {
    super(props)
    this.contentEditable = React.createRef();
    this.state = {
      desc: "",
      recentChange: false,
      savingLoopActive: false
    };
  };

  componentDidUpdate(prevProps) {
    if (this.props.description !== prevProps.description) {
      this.setState({desc: this.props.description})
    }
  }

  saveToDatabaseOrSkip = () => {
    if (this.state.recentChange) {
      this.setState({recentChange: false})
      setTimeout(this.saveToDatabaseOrSkip, 150)
    } else {
      fetch('update_experiment_desc', {
          method: "POST",
          body: JSON.stringify({experiment : this.props.experiment, description: this.state.desc}),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          }
        }).then(res => {
          if (res.status !== 200){
            console.log("Didn't save successfully.")
          }
        })
        this.setState({savingLoopActive: false})
      }
  }

  onFocus = evt => {
    evt.target.style.height = evt.target.scrollHeight + 'px'
  }

  handleChange = evt => {
    evt.target.style.height = evt.target.scrollHeight + 'px'
    this.setState({desc: evt.target.value});
    this.setState({recentChange: true})
    if (this.state.savingLoopActive){
      return
    }
    else {
      this.setState({savingLoopActive: true})
      setTimeout(this.saveToDatabaseOrSkip, 150)
    }
  };


  render = () => {
    return (
      <div style={{padding: "0px 5px 0px 5px"}}>
        <InputLabel  htmlFor="description-box"  >Description</InputLabel>
        <OutlinedInput
          placeholder={"Provide a description of your experiment."}
          id="description-box"
          multiline
          fullWidth={true}
          onChange={this.handleChange}
          value={this.state.desc}
          style={{padding: "10px 5px 10px 5px",  fontSize: "14px", fontFamily: "Roboto", width: "100%", overflow: "hidden"}}
        />
      </div>
    )
  };
};


const ButtonNewExperiment = () => {
  const classes = useStyles();
  const confirm = useConfirm();

  const handleClick = () => {
    confirm({
      description: 'Starting a new experiment will stop data collection for the current experiment. Do you wish to proceed?',
      title: "Starting a new experiment",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary", href: "/start-new-experiment"},
      cancellationButtonProps: {color: "secondary"},
    })
  };

  return (
    <React.Fragment>
      <Button style={{textTransform: 'none', float: "right"}} color="primary" onClick={handleClick}>
        <AddIcon fontSize="15" classes={{root: classes.textIcon}}/> New experiment
      </Button>
    </React.Fragment>
  );
}

const ButtonEndExperiment = () =>{
  const classes = useStyles();
  const confirm = useConfirm();

  const handleClick = () => {
    confirm({
      description: 'This will halt all activities (stirring, dosing, optical density reading, etc.) in all Pioreactor units. You can manually start them again later. Do you wish to end the experiment?',
      title: "End experiment?",
      confirmationText: "Confirm",
      confirmationButtonProps: {color: "primary"},
      cancellationButtonProps: {color: "secondary"},

      }).then(() =>
        fetch("/api/stop_all", {method: "POST"})
    )
  };

  return (
    <React.Fragment>
      <Button style={{textTransform: 'none', float: "right"}} color="primary" onClick={handleClick}>
        <ClearIcon fontSize="15" classes={{root: classes.textIcon}}/> End experiment
      </Button>
    </React.Fragment>
  );
}


function ExperimentSummary(props){
  const classes = useStyles();
  const experiment = props.experimentMetadata.experiment || ""
  const startedAt = props.experimentMetadata.created_at || moment()
  const desc = props.experimentMetadata.description || ""
  const deltaHours = props.experimentMetadata.delta_hours || 0

  return(
    <React.Fragment>
      <div>
        <div className={classes.headerMenu}>
          <Typography variant="h5" component="h1">
            <Box fontWeight="fontWeightBold">{experiment}</Box>
          </Typography>
          <div className={classes.headerButtons}>
            <ButtonNewExperiment/>
            <ButtonEndExperiment/>
            <Button href="/export-data" style={{textTransform: 'none', marginRight: "0px", float: "right"}} color="primary">
              <GetAppIcon fontSize="15" classes={{root: classes.textIcon}}/> Export experiment data
            </Button>
          </div>
        </div>

        <Divider/>
        <Typography variant="subtitle2">

          <Box fontWeight="fontWeightBold" style={{margin: "10px 2px 10px 2px", display:"inline-block"}}>
            <CalendarTodayIcon style={{ fontSize: 12, verticalAlign: "-1px" }}/> Experiment started:
          </Box>
          <Box fontWeight="fontWeightRegular" style={{marginRight: "20px", display:"inline-block"}}>
            <span title={moment(startedAt).format("YYYY-MM-DD HH:mm:ss")}>{moment(startedAt).format("dddd, MMMM D, YYYY")}</span>
          </Box>

          <Box fontWeight="fontWeightBold" style={{margin: "10px 2px 10px 2px", display:"inline-block"}}>
            <TimelapseIcon style={{ fontSize: 12, verticalAlign: "-1px"  }}/>Time elapsed:
          </Box>
          <Box fontWeight="fontWeightRegular" style={{marginRight: "20px", display:"inline-block"}}>
           {deltaHours}h
          </Box>

        </Typography>
      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
          <EditableDescription experiment={experiment} description={desc} />
        </CardContent>
      </Card>
    </React.Fragment>
  )
}


export default ExperimentSummary;
