import React, { useState, Fragment } from 'react';

import {Client, Message} from 'paho-mqtt';

import {makeStyles} from '@material-ui/styles';
import Card from '@material-ui/core/Card';
import CardActions from '@material-ui/core/CardActions';
import CardContent from '@material-ui/core/CardContent';
import Button from '@material-ui/core/Button';
import Typography from '@material-ui/core/Typography';
import FiberManualRecordIcon from '@material-ui/icons/FiberManualRecord';
import { green } from '@material-ui/core/colors';
import Modal from '@material-ui/core/Modal';
import Divider from '@material-ui/core/Divider';
import Slider from '@material-ui/core/Slider';
import TextField from '@material-ui/core/TextField';
import { styled } from '@material-ui/core/styles';

const useStyles = makeStyles({
  root: {
    minWidth: 100,
    marginTop: "15px"
  },
  content:{
    paddingLeft: "15px",
    paddingRight: "15px",
    paddingTop: "10px",
    paddingBottom: "10px",
  },
  unitTitle: {
    fontSize: 17,
    fontFamily: "courier",
    color: "rgba(0, 0, 0, 0.54)"
  },
  unitTitleDisable: {
    fontSize: 17,
    fontFamily: "courier",
    color: "rgba(0, 0, 0, 0.38)"
  },
  pos: {
    marginBottom: 0,
    fontSize: 15,
  },
  footnote: {
    marginBottom: 0,
    fontSize: 12,
  },
  paper: {
    position: 'absolute',
    width: 650,
    backgroundColor: "white",
    border: '2px solid #000',
    padding: 15,
    overflowY: "scroll",
    maxHeight: "80%"
  },
  slider: {
    width: "70%",
    margin: "0 auto"
  },
  divider: {
    marginTop: 10,
    marginBottom: 10,
  },
  textbox: {
      display: "flex",
      fontSize: 13
  },
  alignLeft: {
      flex: 1,
      textAlign: "left",
      fontSize: 13
  },
  alignRight: {
      flex: 1,
      textAlign: "right",
  }
});

function getModalStyle() {
  const top = 50;
  const left = 50;

  return {
    top: `${top}%`,
    left: `${left}%`,
    transform: `translate(-${top}%, -${left}%)`,
  };
}



class UnitSettingDisplay extends React.Component {

  constructor(props) {
    super(props);
    this.state = {msg: this.props.default, isActive: this.props.isActive};
    this.onConnect = this.onConnect.bind(this);
    this.onMessageArrived = this.onMessageArrived.bind(this);
    console.log(this.state.isActive)
  }

  componentDidMount() {
    // need to have unique clientIds
    this.client = new Client("localhost", 9001, "webui" + Math.random());
    this.client.connect({'onSuccess': this.onConnect});
    this.client.onMessageArrived = this.onMessageArrived;
  }

  onConnect() {
      this.client.subscribe("morbidostat/" + this.props.unitNumber + "/" + "Trial-14-d29bfbaee0dd4fb28348c8cb3532cdd0" + "/" + this.props.job + "/" + this.props.attr)
  }

  onMessageArrived(message) {
      this.setState({
        msg: message.payloadString
      });
  }

  render(){
    if (this.props.isBinaryPause) {
      if (this.state.msg === "0"){
        return <div style={{color: "#4caf50"}}>On </div>
      }
      else{
        return <div style={{color: this.state.isActive ? "#f44336" : "grey"}}> Off </div>
      }
    }
    else{
      return(
          <div style={{color: "rgba(0, 0, 0, 0.54)"}}>{this.state.msg}</div>
      )
      }
  }
}


function UnitCard(props) {
  const classes = useStyles();
  const unitName = props.name;
  const isActive = props.isActive
  const unitNumber = unitName.slice(-1);
  const [modalStyle] = React.useState(getModalStyle);
  const [open, setOpen] = React.useState(false);

  const handleOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };

  function UnitSettings(props) {
    const config = require('./data/config.json');
    const defaultStirring = config['stirring']["duty_cycle" + unitNumber]

    // MQTT
    var client = new Client("localhost", 9001, "webui");

    client.connect({onSuccess:onConnect});

    function onConnect() {
      console.log("onConnect");
    }


    function setPauseState(job, state) {
      return function () {
        var message = new Message(String(state));
        message.destinationName = "morbidostat/" + unitNumber + "/Trial-14-d29bfbaee0dd4fb28348c8cb3532cdd0/" + job + "/pause";
        client.send(message);
      };
    }

    function setMorbidostatJobState(job_attr, value) {
        var message = new Message(String(value));
        message.destinationName = "morbidostat/" + unitNumber + "/Trial-14-d29bfbaee0dd4fb28348c8cb3532cdd0/" + job_attr ;
        client.send(message);
    }

    function setMorbidostatJobStateOnEnter(e) {
        if (e.key === 'Enter') {
          setMorbidostatJobState(e.target.id, e.target.value)
          e.target.value = "Updated!"
      }
    }

    function setMorbidostatStirring(e, value){
        setMorbidostatJobState("stirring/duty_cycle", value)
    }


    return (
    <Card style={modalStyle} className={classes.paper}>
     <CardContent>
      <Typography className={classes.unitTitle} color="textSecondary" gutterBottom>
        {unitName}
      </Typography>
      <Divider  className={classes.divider} />
        <Typography color="textSecondary" gutterBottom>
          Optical Density Reading
        </Typography>
        <Typography variant="body2" component="p">
          Pause or start the optical density reading. This will also pause downstream jobs that rely on optical density readings, like growth rates.
        </Typography>
        <Button disableElevation color="secondary" onClick={setPauseState("od_reading", 1)}>Pause</Button>
        <Button disableElevation color="primary" onClick={setPauseState("od_reading", 0)}>Restart</Button>
      <Divider className={classes.divider} />
        <Typography color="textSecondary" gutterBottom>
          Input/Output Events
        </Typography>
        <Typography variant="body2" component="p">
          Pause media input/output events from occuring, or restart them.
        </Typography>
        <Button disableElevation color="secondary" onClick={setPauseState("io_controlling", 1)}>Pause</Button>
        <Button disableElevation color="primary" onClick={setPauseState("io_controlling", 0)}>Restart</Button>
      <Divider  className={classes.divider} />
        <Typography color="textSecondary" gutterBottom>
          Stirring
        </Typography>
        <Typography variant="body2" component="p">
          Modify the stirring speed (arbitrary units). This will effect the optical density reading. Too low and the fan may completely stop.
        </Typography>
        <div className={classes.slider}>
          <Slider
            defaultValue={defaultStirring}
            aria-labelledby="discrete-slider-custom"
            step={1}
            valueLabelDisplay="auto"
            id="stirring/duty_cycle"
            onChangeCommitted={setMorbidostatStirring}
            marks={[{value: 0, label: 0}, {value: defaultStirring, label: "Default: " + defaultStirring}, {value: 100, label: 100}]}
          />
        </div>
        <Typography className={classes.footnote} color="textSecondary">
          Default values are defined in the <code>config.ini</code> file.
        </Typography>
      <Divider className={classes.divider} />
        <Typography color="textSecondary" gutterBottom>
          Volume per dilution
        </Typography>
        <Typography variant="body2" component="p">
          Change the volume per dilution.
        </Typography>
        <TextField size="small" id="io_controlling/volume" label="mL" variant="outlined" onKeyPress={setMorbidostatJobStateOnEnter}/>
      <Divider  className={classes.divider} />
      <Typography color="textSecondary" gutterBottom>
          Target optical density
        </Typography>
        <Typography variant="body2" component="p">
          Change the target optical density.
        </Typography>
        <TextField size="small" id="io_controlling/target_od" label="optical density" variant="outlined" onKeyPress={setMorbidostatJobStateOnEnter}/>
      <Divider  className={classes.divider} />
      <Typography color="textSecondary" gutterBottom>
          Target growth rate
        </Typography>
        <Typography variant="body2" component="p">
          Change the target growth rate - only applicable in <code>morbidostat</code> mode.
        </Typography>
        <TextField size="small" id="io_controlling/target_growth_rate" label="h⁻¹" variant="outlined" onKeyPress={setMorbidostatJobStateOnEnter}/>
      <Divider  className={classes.divider} />
     </CardContent>
    </Card>
  )};

  return (
    <Card className={classes.root} variant={!isActive ? "outlined" : null}>
      <CardContent className={classes.content}>
        <Typography className={isActive ? classes.unitTitle : classes.unitTitleDisable}>
          {unitName}
        </Typography>
        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Stirring:</Typography>
          <UnitSettingDisplay isActive={isActive} default={"-"} className={classes.alignRight} job="stirring" attr="duty_cycle" unitNumber={unitNumber}/>
        </div>
        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Optical density reading:</Typography>
          <UnitSettingDisplay isActive={isActive} default={"-"} className={classes.alignRight} isBinaryPause job="od_reading" attr="pause" unitNumber={unitNumber}/>
        </div>
        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">IO events:</Typography>
          <UnitSettingDisplay isActive={isActive} className={classes.alignRight} isBinaryPause job="io_controlling" attr="pause" unitNumber={unitNumber}/>
        </div>
        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Target optical density:</Typography>
          <UnitSettingDisplay isActive={isActive} default={"-"} className={classes.alignRight} job="io_controlling" attr="target_od" unitNumber={unitNumber}/>
        </div>
        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Target growth rate: </Typography>
          <UnitSettingDisplay isActive={isActive} default={"-"} className={classes.alignRight} job="io_controlling" attr="target_growth_rate" unitNumber={unitNumber}/>
        </div>
      </CardContent>
      <CardActions>
        <Button size="small" color="primary" disabled={!isActive} onClick={handleOpen}>Settings</Button>
          <Modal
            open={open}
            onClose={handleClose}
            aria-labelledby="simple-modal-title"
            aria-describedby="simple-modal-description"
            >
            <UnitSettings/>
          </Modal>
      </CardActions>

    </Card>
  );
}


function UnitCards(props) {
    const classes = useStyles();
    return (
    <div>
      {props.units.map((unit) =>
      <UnitCard name={"morbidostat" + unit} isActive={[1, 2, 3].includes(unit)} />
    )}
    </div>
    )
}

export default UnitCards;
