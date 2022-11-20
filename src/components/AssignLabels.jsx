import React from "react";
import Grid from '@mui/material/Grid';
import FlareIcon from '@mui/icons-material/Flare';
import { Client, Message } from "paho-mqtt";
import clsx from 'clsx';
import {useState, useEffect} from "react";
import { makeStyles } from '@mui/styles';
import Button from "@mui/material/Button";
import TextField from '@mui/material/TextField';
import Divider from '@mui/material/Divider';
import PioreactorIcon from "./PioreactorIcon"
import { Link } from 'react-router-dom';


const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px"
  },
  cardContent: {
    padding: "10px"
  },
  button: {
    marginRight: theme.spacing(1),
  },
  textField:{
    marginTop: theme.spacing(1),
    marginBottom: theme.spacing(1),
    width: "100%"

  },
}));

function FlashLEDButton(props){
  const classes = useStyles();

  const [flashing, setFlashing] = useState(false)


  const onClick = () => {
    setFlashing(true)
    const sendMessage = () => {
      var message = new Message("1");
      message.destinationName = [
        "pioreactor",
        props.unit,
        "$experiment",
        "monitor",
        "flicker_led_response_okay",
      ].join("/");
      message.qos = 0;
      try{
        props.client.publish(message);
      }
      catch (e){
        console.log(e)
        setTimeout(() => {sendMessage()}, 1000)
      }
    }

    sendMessage()
    setTimeout(() => {setFlashing(false)}, 3600 ) // .9 * 4
  }

  return (
    <Button style={{textTransform: 'none', float: "right"}} className={clsx({blinkled: flashing})} disabled={props.disabled} onClick={onClick} color="primary">
      <FlareIcon color={props.disabled ? "disabled" : "primary"} fontSize="15" classes={{root: classes.textIcon}}/> <span > Identify </span>
    </Button>
)}

function AssignLabels(props){
  const classes = useStyles();
  const [labels, setLabels] = useState({})
  const [client, setClient] = useState(null)
  const activeUnits = props.config['cluster.inventory'] ? Object.entries(props.config['cluster.inventory']).filter((v) => v[1] === "1").map((v) => v[0]) : []


  useEffect(() => {
    var client
    if (props.config.remote && props.config.remote.ws_url) {
      client = new Client(
        `ws://${props.config.remote.ws_url}/`,
        "webui_publishExpNameToMQTT" + Math.random()
      )}
    else {
      client = new Client(
        `${props.config['cluster.topology']['leader_address']}`, 9001,
        "webui_publishExpNameToMQTT" + Math.random()
      );
    }
    client.connect();
    setClient(client)
  },[props.config])


  const onSubmit = () => {
    Object.entries(labels).map(unit_label => (
      fetch('/api/update_current_unit_labels',{
            method: "POST",
            body: JSON.stringify({label: unit_label[1], unit: unit_label[0]}),
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json'
            }
        })
    ))
  }
  const onLabelChange = (unit) => (e) => setLabels({...labels, [unit]: e.target.value})


  return (
    <div className={classes.root}>

      <Grid container spacing={1}>

        <Grid item xs={12}>
          <p> Assign labels to Pioreactors in your cluster. These labels are temporary, and will show up in charts, tables, and elsewhere in the interface. Labels can be changed later.</p>
          <Divider style={{marginBottom: "20px"}}/>
        </Grid>


          {activeUnits.map((unit) => (
              <React.Fragment key={unit}>
              <Grid item lg={2} md={1}  xs={0}/>
              <Grid item lg={8} md={10}  xs={12}>
                <div style={{display: "flex", flexWrap: "wrap", justifyContent:"space-between"}}>
                  <div style={{width: "140px"}}>
                    <PioreactorIcon style={{verticalAlign: "middle", fontSize: "1.0em"}}/>
                    <span style={{lineHeight: "40px"}}>{unit}</span>
                  </div>
                  <div>
                    <TextField size="small" placeholder="(Optional)" onChange={onLabelChange(unit)} style={{width: "140px", marginRight: "10px"}}/>
                  </div>
                  <div>
                    <FlashLEDButton client={client} disable={false} config={props.config} unit={unit}/>
                  </div>
                </div>
              </Grid>
              <Grid item lg={2} md={1} xs={0}/>
              </React.Fragment>
            )
            )}
          <Grid item xs={12} lg={4}/>
          <Grid item xs={12} lg={8}>
            <div style={{display: "flex", justifyContent: "flex-end"}}>
              <Button to="/overview" component={Link} variant="contained" color="primary" onClick={onSubmit}> Assign </Button>
            </div>
          </Grid>
      </Grid>

    </div>
  );}


export default AssignLabels;
