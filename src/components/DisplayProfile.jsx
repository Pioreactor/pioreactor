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
    backgroundColor: "rgb(247,247,247)",
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
  else if (hoursElapsed < 1){
    return `${actionType} after ${Math.round(hoursElapsed * 60)} minutes`
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
        <Typography variant="body2">
            <b>Author:</b> {data.metadata.author}
        </Typography>
        <Typography variant="body2">
            <b>Description:</b> {data.metadata.description}
        </Typography>
        {data.labels && Object.keys(data.labels).length > 0 && (
          <>
          <Typography variant="body2">
              <b>Labels:</b>
          </Typography>
          {Object.keys(data.labels).map(worker => (
              <Typography key={worker} variant="body2" style={{ marginLeft: '2em' }}>
                  {worker}: {data.labels[worker]}
              </Typography>

          ))}
          </>
        )}

        <Typography variant="body2">
            <b>Common:</b>
        </Typography>
        {data.common && Object.keys(data.common).map(job => (
            <>
              <Typography key={job} variant="body2" style={{ marginLeft: '2em' }}>
                  <b>Job</b>: {job}
              </Typography>
              {data.common[job].actions.map((action, index) => (
                  <>
                    <Typography key={`common-action-${index}`} variant="body2" style={{ marginLeft: '4em' }}>
                        <b>Action {index + 1}</b>: {humanReadableDuration(action.type, action.hours_elapsed)}
                    </Typography>
                      {Object.keys(action.options).map((option, index) => (
                      <Typography key={`common-${option}-${action}-${index}`} variant="body2" style={{ marginLeft: '8em' }}>
                        {option}: {action.options[option]}
                      </Typography>
                      ))}
                  </>
              ))}
            </>
        ))}

        {data.pioreactors && Object.keys(data.pioreactors).map(pioreactor => (
            <>
                <Typography key={pioreactor} variant="body2">
                    <b>Pioreactor</b>: {pioreactor}
                </Typography>
                {Object.keys(data.pioreactors[pioreactor].jobs).map(job => (
                    <>
                      <Typography key={`${pioreactor}-${job}`}  variant="body2" style={{ marginLeft: '2em' }}>
                          <b>Job</b>: {job}
                      </Typography>
                      {data.pioreactors[pioreactor].jobs[job].actions.map((action, index) => (
                          <>
                            <Typography key={`${pioreactor}-action-${index}`} variant="body2" style={{ marginLeft: '4em' }}>
                                <b>Action {index + 1}</b>: {humanReadableDuration(action.type, action.hours_elapsed)}
                            </Typography>
                              {Object.keys(action.options).map( (option, index) => (
                              <Typography key={`${pioreactor}-${option}-${action}-${index}`} variant="body2" style={{ marginLeft: '8em' }}>
                                {option}: {action.options[option]}
                              </Typography>
                              ))}
                          </>
                      ))}
                    </>
                ))}
            </>
        ))}
      </CardContent>
    </Card>
  );
};


export default DisplayProfile;

