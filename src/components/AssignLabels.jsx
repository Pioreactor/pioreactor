import React from "react";
import Grid from '@mui/material/Grid';
import FlareIcon from '@mui/icons-material/Flare';
import clsx from 'clsx';
import {useState} from "react";
import { makeStyles } from '@mui/styles';
import Button from "@mui/material/Button";
import TextField from '@mui/material/TextField';
import Divider from '@mui/material/Divider';
import PioreactorIcon from "./PioreactorIcon"
import EditIcon from '@mui/icons-material/Edit';
import {getRelabelMap} from "../utilities"
import CheckIcon from '@mui/icons-material/Check';
import { useMQTT } from '../MQTTContext';


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
      const topic = `pioreactor/${props.unit}/$experiment/monitor/flicker_led_response_okay`;
      try{
        props.client.publish(topic, "1", {qos: 0})
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
  const [relabelMap, setRelabelMap] = useState({})
  const {client } = useMQTT();
  const [confirmed, setConfirmed] = useState(false)
  const activeUnits = props.config['cluster.inventory'] ? Object.entries(props.config['cluster.inventory']).filter((v) => v[1] === "1").map((v) => v[0]) : []


  React.useEffect(() => {
    getRelabelMap(setRelabelMap)
  }, [])


  const onSubmit = () => {
    Object.entries(labels).map(unit_label => (
      fetch('/api/unit_labels/current',{
            method: "PUT",
            body: JSON.stringify({label: unit_label[1], unit: unit_label[0]}),
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json'
            }
        })
    ))
    setConfirmed(true)
  }

  const onLabelChange = (unit) => (e) => setLabels({...labels, [unit]: e.target.value})
  const count = Object.values(labels).reduce((accumulator, value) => accumulator + (value !== ""), 0)

  return (
    <div className={classes.root}>

      <Grid container spacing={1}>

        <Grid item xs={12}>
          <p> Assign labels to Pioreactors in your cluster. These labels are temporary for this experiment, and will show up in charts, tables, and elsewhere in this interface.  </p>

          <p>Labels can be changed later, too.</p>
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
                    <TextField size="small" defaultValue={relabelMap[unit]} placeholder="(Optional)" onChange={onLabelChange(unit)} style={{width: "140px", marginRight: "10px"}}/>
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
              <Button
                variant="contained"
                color="primary"
                onClick={onSubmit}
                endIcon={confirmed ? <CheckIcon /> : <EditIcon /> }
                disabled={(count === 0) || confirmed}
              >
                   {confirmed ? "Assigned" : (count > 0 ? `Assign ${count}` : "Assign")}
               </Button>
            </div>
          </Grid>
      </Grid>

    </div>
  );}


export default AssignLabels;
