import React, {useState}  from 'react';

import {Client, Message} from 'paho-mqtt';

import {makeStyles} from '@material-ui/styles';
import Card from '@material-ui/core/Card';
import CardActions from '@material-ui/core/CardActions';
import CardContent from '@material-ui/core/CardContent';
import Button from '@material-ui/core/Button';
import Typography from '@material-ui/core/Typography';
import Modal from '@material-ui/core/Modal';
import Divider from '@material-ui/core/Divider';
import Slider from '@material-ui/core/Slider';
import TextField from '@material-ui/core/TextField';

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
    margin: "40px auto 0px auto"
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
  },
  actionTextField: {
    padding: "0px 10px 0px 0px"
  },
  actionForm: {
    padding: "20px 0px 0px 0px"
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
    this.state = {msg: this.props.default, isUnitActive: this.props.isUnitActive};
    this.onConnect = this.onConnect.bind(this);
    this.onMessageArrived = this.onMessageArrived.bind(this);
  }

  updateParent(data) {
      this.props.passChildData(data);
  }

  componentDidMount() {
    // need to have unique clientIds
    this.client = new Client("ws://morbidostatws.ngrok.io/", "webui" + Math.random());
    this.client.connect({'onSuccess': this.onConnect});
    this.client.onMessageArrived = this.onMessageArrived;
  }

  onConnect() {
    this.client.subscribe(["morbidostat", this.props.unitNumber, this.props.experiment, this.props.job, this.props.attr].join("/"), {qos: 1})
  }

  onMessageArrived(message) {
    this.setState({
      msg: message.payloadString
    });
    this.updateParent(message.payloadString)
  }

  render(){
    if (this.props.isBinaryActive) {
      if (!this.state.isUnitActive) {
        return <div style={{color: "grey"}}> {this.state.msg} </div>
      }
      else {
        if (this.state.msg === "1"){
          return <div style={{color: "#4caf50"}}> On </div>
        }
        else if (this.state.msg === "0") {
          return <div style={{color: "grey"}}> Off </div>
        }
        else{
          return <div style={{color: "grey"}}> {this.state.msg} </div>
        }
      }
    }
    else{
      return(
          <div style={{color: "rgba(0, 0, 0, 0.54)"}}>{this.state.msg}</div>
      )
      }
  }
}

function ModalUnitSettings(props) {
  const classes = useStyles();
  const config = require('./data/config.json');
  const defaultStirring = config['stirring']["duty_cycle" + props.unitNumber]
  const [modalStyle] = React.useState(getModalStyle);

  // MQTT - client ids should be unique
  var client = new Client("ws://morbidostatws.ngrok.io/", "webui" + Math.random());

  client.connect({onSuccess: onConnect});

  function onConnect() {
    console.log("Modal unit setting connected")
  }

  function setActiveState(job, state) {
    return function () {
      var message = new Message(String(state));
      message.destinationName = ["morbidostat", props.unitNumber, props.experiment, job, "active", "set"].join("/");
      message.qos = 1
      client.publish(message);
    };
  }

  function setMorbidostatJobState(job_attr, value) {
      var message = new Message(String(value));
      message.destinationName = ["morbidostat", props.unitNumber, props.experiment, job_attr, "set"].join("/");
      message.qos = 1
      client.publish(message);
  }

  function setMorbidostatJobStateOnEnter(e) {
      if (e.key === 'Enter') {
        setMorbidostatJobState(e.target.id, e.target.value)
        e.target.value = ""
    }
  }

  function setMorbidostatStirring(e, value){
      setMorbidostatJobState("stirring/duty_cycle", value)
  }


  return (
  <Card style={modalStyle} className={classes.paper}>
   <CardContent>
    <Typography className={classes.unitTitle} color="textSecondary" gutterBottom>
      {props.unitName}
    </Typography>
    <Divider  className={classes.divider} />
      <Typography color="textSecondary" gutterBottom>
        Optical density reading
      </Typography>
      <Typography variant="body2" component="p">
        Pause or restart the optical density reading. This will also pause downstream jobs that rely on optical density readings, like growth rates.
      </Typography>
      <Button disableElevation disabled={props.ODReadingActiveState === "0"} color="secondary" onClick={setActiveState("od_reading", 0)}>Pause</Button>
      <Button disableElevation disabled={props.ODReadingActiveState === "1"} color="primary" onClick={setActiveState("od_reading", 1)}>Start</Button>
    <Divider className={classes.divider} />
    <Typography color="textSecondary" gutterBottom>
        Growth rate calculating
      </Typography>
      <Typography variant="body2" component="p">
        Pause or start the calculating the implied growth rate and smooted optical densities.
      </Typography>
      <Button disableElevation disabled={props.growthRateActiveState === "0"} color="secondary" onClick={setActiveState("growth_rate_calculating", 0)}>Pause</Button>
      <Button disableElevation disabled={props.growthRateActiveState === "1"} color="primary" onClick={setActiveState("growth_rate_calculating", 1)}>Start</Button>
    <Divider className={classes.divider} />
      <Typography color="textSecondary" gutterBottom>
        Input/output events
      </Typography>
      <Typography variant="body2" component="p">
        Pause media input/output events from occuring, or restart them.
      </Typography>
      <Button disableElevation disabled={props.IOEventsActiveState === "0"} color="secondary" onClick={setActiveState("io_controlling", 0)}>Pause</Button>
      <Button disableElevation disabled={props.IOEventsActiveState === "1"} color="primary" onClick={setActiveState("io_controlling", 1)}>Start</Button>
    <Divider  className={classes.divider} />
      <Typography color="textSecondary" gutterBottom>
        Stirring
      </Typography>
      <Typography variant="body2" component="p">
        Modify the stirring speed (arbitrary units). This will effect the optical density reading. Too low and the fan may completely stop.
      </Typography>
      <div className={classes.slider}>
        <Slider
          defaultValue={props.stirringState}
          aria-labelledby="discrete-slider-custom"
          step={1}
          valueLabelDisplay="on"
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
        Change the volume per dilution. Typical values are between 0.0mL and 1.5mL.
      </Typography>
      <TextField size="small" id="io_controlling/volume" label="mL" variant="outlined" onKeyPress={setMorbidostatJobStateOnEnter}/>
    <Divider  className={classes.divider} />
    <Typography color="textSecondary" gutterBottom>
        Target optical density
      </Typography>
      <Typography variant="body2" component="p">
        Change the target optical density. Typical values are between 1.0 and 2.5 (arbitrary units)
      </Typography>
      <TextField size="small" id="io_controlling/target_od" helperText={"Current value: " + props.targetODState + "AU"} label="optical density" variant="outlined" onKeyPress={setMorbidostatJobStateOnEnter}/>
    <Divider  className={classes.divider} />
    <Typography color="textSecondary" gutterBottom>
        Target growth rate
      </Typography>
      <Typography variant="body2" component="p">
        Change the target hourly growth rate - only applicable in <code>morbidostat</code> mode. Typical values are between 0.05h⁻¹ and 0.4h⁻¹.
      </Typography>
      <TextField size="small" id="io_controlling/target_growth_rate" label="h⁻¹" helperText={"Current value: " + props.targetGrowthRateState + "h⁻¹"} variant="outlined" onKeyPress={setMorbidostatJobStateOnEnter}/>
    <Divider  className={classes.divider} />
   </CardContent>
  </Card>
)};


function ActionPumpForm(props) {
  const emptyState = ""
  const [mL, setML] = useState(emptyState);
  const [duration, setDuration] = useState(emptyState);
  const classes = useStyles();
  const [isMLDisabled, setIsMLDisabled] = useState(false);
  const [isDurationDisabled, setIsDurationDisabled] = useState(false);


  function onSubmit(e) {
    e.preventDefault()
    if ((mL !== emptyState) || (duration !== emptyState)){
      const params = (mL !== "") ?  {mL: mL} : {duration: duration}
      fetch("/" + props.action + "/" + props.unitName + "?" + new URLSearchParams(params))
    }
  }

  function handleMLChange(e) {
    setML(e.target.value);
    setIsDurationDisabled(true);
    if (e.target.value === emptyState){
      setIsDurationDisabled(false)
    }
  }

  function handleDurationChange(e) {
    setDuration(e.target.value);
    setIsMLDisabled(true);
    if (e.target.value === emptyState){
      setIsMLDisabled(false)
    }
  }


  return (
    <form id={props.action} className={classes.actionForm}>
      <TextField
        name="mL"
        value={mL}
        size="small"
        id={props.action + "_mL"}
        label="mL"
        variant="outlined"
        disabled={isMLDisabled}
        onChange={handleMLChange}
        className={classes.actionTextField}

      />
      <TextField
        name="duration"
        value={duration}
        size="small"
        id={props.action + "_duration"}
        label="seconds"
        variant="outlined"
        disabled={isDurationDisabled}
        onChange={handleDurationChange}
        className={classes.actionTextField}

      />
      <br/>
      <br/>
      <Button type="submit" variant="contained" color="primary" className={classes.button} onClick={onSubmit}>
        Run
      </Button>
    </form>
  )
}

function ModalUnitActions(props) {
  const classes = useStyles();
  const [modalStyle] = useState(getModalStyle);

  return (
  <Card style={modalStyle} className={classes.paper}>
   <CardContent>
    <Typography className={classes.unitTitle} color="textSecondary" gutterBottom>
      {props.unitName}
    </Typography>
    <Divider className={classes.divider} />
    <Typography color="textSecondary" gutterBottom>
      Add media
    </Typography>
    <Typography variant="body2" component="p">
      Run the media pump for a set duration (seconds), or a set volume (mL).
    </Typography>
    <ActionPumpForm action="add_media" unitName={props.unitName}/>
    <Divider  className={classes.divider} />
    <Typography color="textSecondary" gutterBottom>
      Add alternative media
    </Typography>
    <Typography variant="body2" component="p">
      Run the alternative media pump for a set duration (seconds), or a set volume (mL).
    </Typography>
    <ActionPumpForm action="add_alt_media" unitName={props.unitName}/>
    <Divider  className={classes.divider} />
    <Typography color="textSecondary" gutterBottom>
      Remove waste
    </Typography>
    <Typography variant="body2" component="p">
      Run the waste pump for a set duration (seconds), or a set volume (mL).
    </Typography>
    <ActionPumpForm action="add_media" unitName={props.unitName}/>
    <Divider  className={classes.divider} />
   </CardContent>
  </Card>
)};


function UnitCard(props) {
  const classes = useStyles();
  const unitName = props.name;
  const isUnitActive = props.isUnitActive
  const unitNumber = unitName.slice(-1);
  const experiment = "Trial-21-3b9c958debdc40ba80c279f8463a4cf7"

  const [settingModelOpen, setSettingModalOpen] = useState(false);
  const [actionModelOpen, setActionModalOpen] = useState(false);

  const [stirringState, setStirringState] = useState(0);
  const [ODReadingActiveState, setODReadingActiveState] = useState("0");
  const [growthRateActiveState, setGrowthRateActiveState] = useState("0");
  const [IOEventsActiveState, setIOEventsActiveState] = useState("0");
  const [targetODState, setTargetODState] = useState(0);
  const [targetGrowthRateState, setTargetGrowthRateState] = useState("0");


  const handleSettingModalOpen = () => {
    setSettingModalOpen(true);
  };

  const handleSettingModalClose = () => {
    setSettingModalOpen(false);
  };


  const handleActionModalOpen = () => {
    setActionModalOpen(true);
  };

  const handleActionModalClose = () => {
    setActionModalOpen(false);
  };


  return (
    <Card className={classes.root} variant={!isUnitActive ? "outlined" : null}>
      <CardContent className={classes.content}>
        <Typography className={isUnitActive ? classes.unitTitle : classes.unitTitleDisable}>
          {unitName}
        </Typography>

        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Stirring speed:</Typography>
          <UnitSettingDisplay passChildData={setStirringState} experiment={experiment} isUnitActive={isUnitActive} default={"-"} className={classes.alignRight} job="stirring" attr="duty_cycle" unitNumber={unitNumber}/>
        </div>

        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Optical density reading:</Typography>
          <UnitSettingDisplay passChildData={setODReadingActiveState} experiment={experiment} isUnitActive={isUnitActive} default={"Off"} className={classes.alignRight} isBinaryActive job="od_reading" attr="active" unitNumber={unitNumber}/>
        </div>

        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Growth rate:</Typography>
          <UnitSettingDisplay passChildData={setGrowthRateActiveState} experiment={experiment} isUnitActive={isUnitActive} default={"Off"} className={classes.alignRight} isBinaryActive job="growth_rate_calculating" attr="active" unitNumber={unitNumber}/>
        </div>

        <div className={classes.textbox}>
          <Typography className={classes.alignLeft} color="textPrimary">IO events:</Typography>
          <UnitSettingDisplay passChildData={setIOEventsActiveState} experiment={experiment} isUnitActive={isUnitActive} default={"Off"} className={classes.alignRight} isBinaryActive job="io_controlling" attr="active" unitNumber={unitNumber}/>
        </div>

        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Target optical density:</Typography>
          <UnitSettingDisplay experiment={experiment} passChildData={setTargetODState} isUnitActive={isUnitActive} default={"-"} className={classes.alignRight} job="io_controlling" attr="target_od" unitNumber={unitNumber}/>
        </div>

        <div className={classes.textbox}>
          <Typography className={classes.alignLeft}  color="textPrimary">Target growth rate: </Typography>
          <UnitSettingDisplay experiment={experiment} passChildData={setTargetGrowthRateState} isUnitActive={isUnitActive} default={"-"} className={classes.alignRight} job="io_controlling" attr="target_growth_rate" unitNumber={unitNumber}/>
        </div>

      </CardContent>
      <CardActions>
        <Button size="small" color="primary" disabled={!isUnitActive} onClick={handleSettingModalOpen}>Settings</Button>
          <Modal
            open={settingModelOpen}
            onClose={handleSettingModalClose}
            aria-labelledby="simple-modal-title"
            aria-describedby="simple-modal-description"
            >
            <ModalUnitSettings
              stirringState={stirringState}
              ODReadingActiveState={ODReadingActiveState}
              growthRateActiveState={growthRateActiveState}
              IOEventsActiveState={IOEventsActiveState}
              targetGrowthRateState={targetGrowthRateState}
              targetODState={targetODState}
              experiment={experiment}
              unitName={unitName}
              unitNumber={unitNumber}/>
          </Modal>
        <Button size="small" color="primary" disabled={!isUnitActive} onClick={handleActionModalOpen}>Actions</Button>
          <Modal
            open={actionModelOpen}
            onClose={handleActionModalClose}
            aria-labelledby="simple-modal-title"
            aria-describedby="simple-modal-description"
            >
            <ModalUnitActions
              experiment={experiment}
              unitName={unitName}
              unitNumber={unitNumber}/>
          </Modal>
      </CardActions>
    </Card>
  );
}


function UnitCards(props) {
    return (
    <div>
      {props.units.map((unit) =>
      <UnitCard key={"morbidostat" + unit} name={"morbidostat" + unit} isUnitActive={[1, 2, 3].includes(unit)} />
    )}
    </div>
    )
}

export default UnitCards;
