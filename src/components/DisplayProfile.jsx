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
    backgroundColor: "rgb(248,248,248)",
    letterSpacing: "0em",
    margin: "10px auto 10px auto",
    position: "relative",
    width: "98%",
    border: "1px solid #ccc",
    borderRadius: "0px",
    boxShadow: "none"
  },
}));


const humanReadableDuration = (actionType, hoursElapsed) => {
  if (hoursElapsed === 0){
    return `${actionType} immediately`
  }
  else if (hoursElapsed < 1./60){
    return `${actionType} after ${Math.round(hoursElapsed * 60 * 60 * 10) / 10} seconds`
  }
  else if (hoursElapsed < 1){
    return `${actionType} after ${Math.round(hoursElapsed * 60 * 10) / 10} minutes`
  }
  else if (hoursElapsed === 1){
    return `${actionType} after ${hoursElapsed} hour`
  }
  else {
    return `${actionType} after ${hoursElapsed} hours`
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
        <Typography sx={{ mb: 1.5 }} color="text.secondary" gutterBottom>
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

        {data.labels && Object.keys(data.labels).length > 0 && (
          <>
          <Typography variant="body2">
              <b>Assign labels:</b>
          </Typography>
          {Object.keys(data.labels).map(worker => (
              <Typography key={worker} variant="body2" style={{ marginLeft: '2em' }}>
                  {worker} ⇝ {data.labels[worker]}
              </Typography>
          ))}
          <br/>
          </>
        )}



        {Object.keys(data.common).length > 0 &&
         <>
          <Typography variant="body2">
              <b>All Pioreactor(s) do:</b>
          </Typography>
          {data.common && Object.keys(data.common).map(job => (
              <React.Fragment key={job}>
                <Typography  variant="body2" style={{ marginLeft: '2em' }}>
                    <b> {job}</b>:
                </Typography>
                {data.common[job].actions.sort((a, b) => a.hours_elapsed > b.hours_elapsed).map((action, index) => (
                    <React.Fragment key={`common-action-${index}`}>
                      <Typography variant="body2" style={{ marginLeft: '4em' }}>
                          {index + 1}: {humanReadableDuration(action.type, action.hours_elapsed)}
                      </Typography>
                        {Object.keys(action.options || {}).map((option, index) => (
                          <Typography key={`common-${option}-${action}-${index}`} variant="body2" style={{ marginLeft: '8em' }}>
                            {option}: {action.options[option]}
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
                <Typography variant="body2">
                  <b>Pioreactor { pioreactor in data.labels ?
                        <>{data.labels[pioreactor]} does:</>
                      : <>{pioreactor} does:</>
                  }</b>
                </Typography>
                {Object.keys(data.pioreactors[pioreactor].jobs).map(job => (
                    <React.Fragment key={`${pioreactor}-${job}`}>
                      <Typography key={`${pioreactor}-${job}`}  variant="body2" style={{ marginLeft: '2em' }}>
                          <b> {job}</b>:
                      </Typography>
                      {data.pioreactors[pioreactor].jobs[job].actions.sort((a, b) => a.hours_elapsed > b.hours_elapsed).map((action, index) => (
                          <React.Fragment key={`${pioreactor}-action-${index}`}>
                            <Typography variant="body2" style={{ marginLeft: '4em' }}>
                                {index + 1}: {humanReadableDuration(action.type, action.hours_elapsed)}
                            </Typography>
                              {Object.keys(action.options || {}).map( (option, index) => (
                                <Typography key={`${pioreactor}-${option}-${action}-${index}`} variant="body2" style={{ marginLeft: '6em' }}>
                                  set {option} to {action.options[option]}
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

