import React from "react";
import { makeStyles } from '@mui/styles';
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';

const useStyles = makeStyles((theme) => ({
  cardContent: {
    padding: "10px"
  },
  DisplayProfileCard: {
    maxHeight: "350px",
    overflow: "auto",
    backgroundColor: "rgb(250,250,250)",
    letterSpacing: "0em",
    margin: "10px auto 10px auto",
    position: "relative",
    width: "98%",
    border: "1px solid #ccc",
    borderRadius: "0px",
    boxShadow: "none"
  },
  highlightedSetting: {
    backgroundColor: "#f3deff3b",
    color: "#872298",
  },
  highlightedTarget: {
    backgroundColor: "#f3deff3b",
    color: "#872298",
  },
  highlightedIf: {
    backgroundColor: "#f3deff3b",
    color: "#872298",
  },
  highlightedActionType: {},
}));


const humanReadableDuration = (hoursElapsed) => {
  if (hoursElapsed === 0){
    return `immediately`
  }
  else if (hoursElapsed < 1./60){
    return `after ${Math.round(hoursElapsed * 60 * 60 * 10) / 10} seconds`
  }
  else if (hoursElapsed < 1){
    return `after ${Math.round(hoursElapsed * 60 * 10) / 10} minutes`
  }
  else if (hoursElapsed === 1){
    return `after ${hoursElapsed} hour`
  }
  else {
    return `after ${hoursElapsed} hours`
  }

}



const DisplayProfile = ({ data }) => {
  const classes = useStyles();
  return (
    <Card className={classes.DisplayProfileCard}>
      <CardContent className={classes.cardContent}>
        <Typography variant="h6">
          {data.experiment_profile_name}
        </Typography>
        <Typography sx={{ mb: 1.5 }} variant="subtitle1" color="text.secondary" gutterBottom>
          Created by {data.metadata.author}
        </Typography>
        {data.metadata.description &&
          <>
            <Typography variant="body2">
                <b>Description:</b> {data.metadata.description}
            </Typography>
            <br/>
          </>
        }

        {data.plugins && data.plugins.length > 0 && (
          <>
          <Typography variant="body2">
              <b>Plugins required:</b>
          </Typography>
          {(data.plugins).map(plugin => (
              <Typography key={plugin.name} variant="body2" style={{ marginLeft: '2em' }}>
                  {plugin.name} {plugin.version}
              </Typography>
          ))}
          <br/>
          </>
        )}



        {Object.keys(data.common).length > 0 &&
         <>
          <Typography variant="subtitle2">
              All Pioreactor(s) do:
          </Typography>
          {data.common && Object.keys(data.common.jobs).map(job => (
              <React.Fragment key={job}>
                <Typography  variant="subtitle2" style={{ marginLeft: '2em' }}>
                    {job}:
                </Typography>
                {data.common.jobs[job].actions.sort((a, b) => a.hours_elapsed > b.hours_elapsed).map((action, index) => (
                    <React.Fragment key={`common-action-${index}`}>
                      <Typography variant="body2" style={{ marginLeft: '4em' }}>
                          {index + 1}: <span class={classes.highlightedActionType}>{action.type}</span> {action.type === "start" ? job : ""} {humanReadableDuration(action.hours_elapsed)}
                      </Typography>
                        {Object.keys(action.options || {}).map((option, index) => (
                          <Typography key={`common-${option}-${action}-${index}`} variant="body2" style={{ marginLeft: '6em' }}>
                            — set <span class={classes.highlightedTarget}>{option}</span> to <span class={classes.highlightedSetting}>{action.options[option]}</span>
                          </Typography>
                        ))}
                    </React.Fragment>
                ))}
              </React.Fragment>
          ))}
          <br/>
          </>
        }
        {Object.keys(data.pioreactors).length > 0 && Object.keys(data.pioreactors).map(pioreactor => (
            <React.Fragment key={pioreactor}>
                <Typography variant="subtitle2">
                  Pioreactor {pioreactor} does:
                </Typography>
                <Typography  variant="body2" style={{ marginLeft: '2em' }}>
                {data.pioreactors[pioreactor].label ?
                   <> Relabel to <span class={classes.highlightedTarget}>{data.pioreactors[pioreactor].label}</span> </> : <></>
                }
                </Typography>
                {Object.keys(data.pioreactors[pioreactor].jobs).map(job => (
                    <React.Fragment key={`${pioreactor}-${job}`}>
                      <Typography key={`${pioreactor}-${job}`}  variant="subtitle2" style={{ marginLeft: '2em' }}>
                          {job}:
                      </Typography>
                      {data.pioreactors[pioreactor].jobs[job].actions.sort((a, b) => a.hours_elapsed > b.hours_elapsed).map((action, index) => (
                          <React.Fragment key={`${pioreactor}-action-${index}`}>
                            <Typography variant="body2" style={{ marginLeft: '4em' }}>
                                {index + 1}: <span class={classes.highlightedActionType}>{action.type}</span> {action.type === "start" ? job : ""}  {humanReadableDuration(action.hours_elapsed)}
                            </Typography>
                            {action.if ?
                            <Typography variant="body2" style={{ marginLeft: '6em' }}>
                                only if <span class={classes.highlightedIf}>{action.if}</span>
                            </Typography>
                             : <></>}
                              {Object.keys(action.options || {}).map( (option, index) => (
                                <Typography key={`${pioreactor}-${option}-${action}-${index}`} variant="body2" style={{ marginLeft: '6em' }}>
                                — set <span class={classes.highlightedTarget}>{option}</span> to <span class={classes.highlightedSetting}>{action.options[option]}</span>
                                </Typography>
                              ))}
                          </React.Fragment>
                      ))}
                    </React.Fragment>
                ))}
              <br/>
            </React.Fragment>
        ))}
      </CardContent>
    </Card>
  );
};



export default DisplayProfile;

