import React from 'react'
import dayjs from "dayjs";
//import dayjs from "dayjs";
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import {Typography} from '@mui/material';
import Box from '@mui/material/Box';
import OutlinedInput from '@mui/material/OutlinedInput';
import InputLabel from '@mui/material/InputLabel';
import Divider from '@mui/material/Divider';
import Alert from '@mui/material/Alert';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import TimelapseIcon from '@mui/icons-material/Timelapse';
import { Link } from 'react-router';
import ManageExperimentMenu from "./ManageExperimentMenu";
import ArrowOutwardIcon from '@mui/icons-material/ArrowOutward';


class EditableDescription extends React.Component {
  constructor(props) {
    super(props);
    this.contentEditable = React.createRef();
    this.state = {
      desc: this.props.experimentMetadata.description,
      recentChange: false,
      savingLoopActive: false,
    };
  }

  componentDidUpdate(prevProps) {
    if (this.props.experimentMetadata !== prevProps.experimentMetadata) {
      this.setState({ desc: this.props.experimentMetadata.description });
    }
  }

  saveToDatabaseOrSkip = () => {
    if (this.state.recentChange) {
      this.setState({recentChange: false})
      setTimeout(this.saveToDatabaseOrSkip, 150)
    } else {
      fetch(`/api/experiments/${this.props.experimentMetadata.experiment}`, {
          method: "PATCH",
          body: JSON.stringify({description: this.state.desc}),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          }
        }).then(res => {
          if (res.ok){
            this.props.updateExperiment({ ...this.props.experimentMetadata, description: this.state.desc });
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
        <InputLabel htmlFor="description-box">Description</InputLabel>
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



function ExperimentSummary({experimentMetadata, updateExperiment, showAssignmentAlert=false}){
  const experiment = experimentMetadata.experiment
  const startedAt = experimentMetadata.created_at
  const deltaHours = experimentMetadata.delta_hours
  return(
    <React.Fragment>
      <Box>
        <Box sx={{display: "flex", justifyContent: "space-between", mb: 1}}>
          <Typography variant="h5" component="h1">
            <Box fontWeight="fontWeightBold">{experiment}</Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <ManageExperimentMenu experiment={experiment}/>
          </Box>
        </Box>

        <Divider/>
        <Box sx={{m: "10px 2px 10px 2px", display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
          <Typography variant="subtitle2" sx={{flexGrow: 1}}>
            <Box sx={{display:"inline"}}>
              <Box fontWeight="fontWeightBold" sx={{display:"inline-block"}}>
                <CalendarTodayIcon sx={{ fontSize: 12, verticalAlign: "-1px" }}/> Experiment created at:&nbsp;
              </Box>
              <Box fontWeight="fontWeightRegular" sx={{mr: "1%", display:"inline-block"}}>
                {(startedAt !== "") &&
                <span>{dayjs(startedAt).format("dddd, MMMM D, h:mm a")}</span>
                }
              </Box>
            </Box>

            <Box sx={{display:"inline"}}>
              <Box fontWeight="fontWeightBold" sx={{display:"inline-block"}}>
                <TimelapseIcon sx={{ fontSize: 12, verticalAlign: "-1px"  }}/> Hours elapsed:&nbsp;
              </Box>
              <Box fontWeight="fontWeightRegular" sx={{mr: "1%", display:"inline-block"}}>
               {deltaHours}h
              </Box>
            </Box>

      </Typography>
        </Box>
      </Box>
      {showAssignmentAlert &&
        <Alert severity="info" sx={{ mb: 1 }}>
          No Pioreactors are currently assigned to this experiment. <Link to="/pioreactors"> Assign Pioreactors</Link>
        </Alert>
      }
      <Card >
        <CardContent sx={{p: 1}}>
          <EditableDescription experimentMetadata={experimentMetadata} updateExperiment={updateExperiment} />
        </CardContent>
      </Card>
    </React.Fragment>
  )
}


export default ExperimentSummary;
