import React from "react";
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';



const DisplayProfileCard = {
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
}

const highlight = {
    backgroundColor: "#f3deff41",
    color: "#872298",
    padding: "1px 3px",
    display: "inline block"
  }

const highlightedSetting = highlight

const highlightedTarget = highlight

const highlightedIf = highlight

const highlightedActionType = {}
const highlightedMessage = {fontStyle: "italic"}

function processBracketedExpression(value) {
    const pattern = /\${{(.*?)}}/;
    const match = pattern.exec(String(value));

    if (match) {
        return match[1]; // Return the content inside the brackets
    } else {
        return value; // Return the original value if no brackets are found
    }
}

const humanReadableDuration = (hoursElapsed) => {
  if (hoursElapsed === 0){
    return `immediately`
  }
  else if (hoursElapsed < 1./60){
    return `${Math.round(hoursElapsed * 60 * 60 * 10) / 10} seconds`
  }
  else if (hoursElapsed < 1){
    return `${Math.round(hoursElapsed * 60 * 10) / 10} minutes`
  }
  else if (hoursElapsed === 1){
    return `${hoursElapsed} hour`
  }
  else {
    return `${hoursElapsed} hours`
  }

}

const after = (hoursElapsed) => {
  if ((hoursElapsed) > 0) {
    return "after"
  }
  else{
    return ""
  }
}


const ActionDetails = ({ action, jobName, index }) => {

  switch (action.type) {
    case 'start':
    case 'update':
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: <span style={highlightedActionType}>{action.type}</span> {jobName} {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)}
          </Typography>
          {action.if && (
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              only if <span style={highlightedIf}>{processBracketedExpression(action.if)}</span>
            </Typography>
          )}
          {Object.keys(action.options || {}).map((option, idx) => {
            const optionValue = action.options[option];
            return (
              <Typography key={`option-${idx}`} variant="body2" style={{ marginLeft: '6em' }}>
                — set <span style={highlightedTarget}>{option}</span>
                {optionValue !== null ? (
                  <> to <span style={highlightedSetting}>{processBracketedExpression(optionValue)}</span></>
                ) : null}
              </Typography>
            );
          })}
        </>
      );
    case 'log':
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: <span style={highlightedActionType}>log</span> {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)} the message:
          </Typography>
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
             "<span style={highlightedMessage}>{action.options['message']}</span>"
            </Typography>
          {action.if && (
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              only if <span style={highlightedIf}>{processBracketedExpression(action.if)}</span>
            </Typography>
          )}
        </>
      );
    case 'stop':
    case 'pause':
    case 'resume':
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: <span style={highlightedActionType}>{action.type}</span> {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)}
          </Typography>
          {action.if && (
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              only if <span style={highlightedIf}>{processBracketedExpression(action.if)}</span>
            </Typography>
          )}
        </>
      );
    case 'repeat':
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)}, <span style={highlightedActionType}>repeat</span> the following every {humanReadableDuration(action.repeat_every_hours)},
          </Typography>
          {action.if && (
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              only if <span style={highlightedIf}>{processBracketedExpression(action.if)}</span>
            </Typography>
          )}
          {action.while && (
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              while <span style={highlightedIf}>{processBracketedExpression(action.while)}</span> {action.max_hours ? "or" : ""}
            </Typography>
          )}
          {action.max_hours && (
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              until {humanReadableDuration(action.max_hours)} have passed
            </Typography>
          )}
          <div style={{ marginLeft: '2em' }}>
          {action.actions.map((action, idx) => (
            <ActionDetails action={action} jobName={jobName} index={idx} />
          ))}
          </div>
        </>
      );
    default:
      return null;
  }
};


const DisplayProfile = ({ data }) => {
  return (
    <Card sx={DisplayProfileCard}>
      <CardContent sx={{padding: "10px"}}>
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


        {Object.keys(data.common.jobs).length > 0 &&
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
                      <ActionDetails key={`common-action-${index}`} action={action} jobName={job} index={index} />
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
                   <> Relabel to <span style={highlightedTarget}>{data.pioreactors[pioreactor].label}</span> </> : <></>
                }
                </Typography>
                  {Object.keys(data.pioreactors[pioreactor].jobs).map(job => (
                    <React.Fragment key={`${pioreactor}-${job}`}>
                      <Typography key={`${pioreactor}-${job}`}  variant="subtitle2" style={{ marginLeft: '2em' }}>
                          {job}:
                      </Typography>
                        {data.pioreactors[pioreactor].jobs[job].actions.sort((a, b) => a.hours_elapsed - b.hours_elapsed).map((action, index) => (
                          <ActionDetails key={`${pioreactor}-action-${index}`} action={action} jobName={job} index={index} />
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

