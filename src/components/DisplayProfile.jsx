import React from "react";
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import Box from '@mui/material/Box';
import CardContent from '@mui/material/CardContent';
import UnderlineSpan from "./UnderlineSpan";

const DisplayProfileCard = {
    height: "350px",
    overflow: "auto",
    backgroundColor: "rgb(250,250,250)",
    letterSpacing: "0em",
    margin: "10px auto 10px auto",
    position: "relative",
    width: "98%",
    border: "1px solid #ccc",
    borderRadius: "4px",
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

function isNumeric(v) {
  if (typeof v != "string") return !Number.isNaN(v)
  return !isNaN(v) && // use type coercion to parse the _entirety_ of the string (`parseFloat` alone does not do this)...
         !isNaN(parseFloat(v)) // ...and ensure strings of whitespace fail
}

function processBracketedExpression(value) {
    const pattern = /\${{(.*?)}}/;
    var match = pattern.exec(String(value));

    if (match) {
        return match[1]; // Return the content inside the brackets
    }
    const almostPattern = /{{(.*?)}}/;
    match = almostPattern.exec(String(value));
    if (match) {
        return "MISSING $ INFRONT"; // Return the content inside the brackets
    }
    return String(value); // Return the original value if no brackets are found
}

const humanReadableDuration = (duration, missingMsg='missing `hours_elapsed` field') => {
  if (duration === undefined || duration === null){
    return <UnderlineSpan title={missingMsg}>after ???</UnderlineSpan>
  }
  else if (!isNumeric(duration)){
    return <UnderlineSpan title={missingMsg}>after ???</UnderlineSpan>
  }
  else if (duration < 0){
    return <UnderlineSpan title={missingMsg}>after ???</UnderlineSpan>
  }
  else if (duration === 0){
    return "immediately"
  }
  else if (duration < 1./60){
    const seconds = Math.round(duration * 60 * 60 * 10) / 10
    return `${seconds} ${seconds === 1 ? 'second' : 'seconds'}`
  }
  else if (duration < 1){
    const minutes = Math.round(duration * 60 * 10) / 10
    return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`
  }
  else if (duration === 1){
    return `${duration} hour`
  }
  else {
    return `${duration} hours`
  }
}

const humanReadableDurationPre = (duration, missingMsg) => {
  if (duration === undefined || duration === null){
    return <UnderlineSpan title={missingMsg}>after ???</UnderlineSpan>
  }
  else if (!isNumeric(duration)){
    return <UnderlineSpan title={missingMsg}>after ???</UnderlineSpan>
  }
  else if (duration < 0){
    return <UnderlineSpan title={missingMsg}>after ???</UnderlineSpan>
  }
  else if (duration === 0){
    return `starting immediately`
  }
  else {
    return humanReadableDuration(duration, missingMsg)
  }
}


const after = (duration) => {
  if ((duration) > 0) {
    return "after"
  }
  else{
    return ""
  }
}


const ActionDetails = ({ action, jobName, index }) => {
  var if_;
  if (action?.if) {
    if_ = <>
            if <span style={highlightedIf}>{processBracketedExpression(action.if)}</span>,
          </>
  } else {
    if_ = <></>
  }

  switch (action?.type) {
    case 'start':
    case 'update':
      const validOptions = (action?.options && (typeof action.options === 'object' && !Array.isArray(action.options)))
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: {if_} <span style={highlightedActionType}>{action.type}</span> <span  style={{ fontWeight: 500 }}>{jobName}</span> {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)}
          </Typography>
          {validOptions  && Object.keys(action.options).map((option, idx) => {
            const optionValue = action.options[option];
            if (typeof optionValue === 'object'){
              // intermediate state when typing
              return <></>
            }
            return (
              <Typography key={`option-${idx}`} variant="body2" style={{ marginLeft: '6em' }}>
                — set <span style={highlightedTarget}>{option}</span>
                {optionValue !== null ? (
                  <> to <span style={highlightedSetting}>{processBracketedExpression(optionValue)}</span></>
                ) : null}
              </Typography>
            );
          })}
          {action?.type === 'update' && (!validOptions) &&
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              <UnderlineSpan title="missing `options` field"> options? </UnderlineSpan>
            </Typography>
          }
        </>
      );
    case 'log':
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: {if_} <span style={highlightedActionType}>log</span> {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)} the message:
          </Typography>
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
             "<span style={highlightedMessage}>{action.options?.message}</span>"
            </Typography>
        </>
      );
    case 'stop':
    case 'pause':
    case 'resume':
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: {if_} <span style={highlightedActionType}>{action.type}</span> {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)}
          </Typography>
        </>
      );
    case 'when':
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: {if_} {after(action.hours_elapsed)} {humanReadableDurationPre(action.hours_elapsed, 'missing `hours_elapsed` field')}, the first time <span style={highlightedActionType}>when</span> <span style={highlightedIf}>{processBracketedExpression(action.condition)}</span>, run:
          </Typography>
          <div style={{ marginLeft: '2em' }}>
          {Array.isArray(action.actions) && action.actions.sort((a, b) => a?.hours_elapsed - b?.hours_elapsed).map((action, index) => (
            <ActionDetails key={index} action={action} jobName={jobName} index={index} />
          ))}
          </div>
        </>
      );
    case 'repeat':
      return (
        <>
          <Typography variant="body2" style={{ marginLeft: '4em' }}>
            {index + 1}: {if_} {after(action.hours_elapsed)} {humanReadableDurationPre(action.hours_elapsed, 'missing `hours_elapsed` field')}, <span style={highlightedActionType}>repeat</span> the following every {humanReadableDuration(action.repeat_every_hours, 'missing `repeat_every_hours` field')},
          </Typography>
          {action.while && (
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              while <span style={highlightedIf}>{processBracketedExpression(action.while)}</span> {action.max_hours ? "or" : ""}
            </Typography>
          )}
          {action.max_hours && (
            <Typography variant="body2" style={{ marginLeft: '6em' }}>
              until {humanReadableDuration(action.max_hours, 'max_hours')} have passed
            </Typography>
          )}
          <div style={{ marginLeft: '2em' }}>
          {Array.isArray(action.actions) && action.actions.sort((a, b) => a?.hours_elapsed - b?.hours_elapsed).map((action, index) => (
            <ActionDetails key={index} action={action} jobName={jobName} index={index} />
          ))}
          </div>
        </>
      );
    default:
      return <>
        <Typography variant="body2" style={{ marginLeft: '4em' }}>
        {index + 1}: {if_} <UnderlineSpan title="type required: one of {start, stop, pause, resume, log, repeat, when}">???</UnderlineSpan>
        </Typography>
      </>;
  }
};


const DescriptionSection = ({ description }) => (
  <>
    {description && (
      <>
        <Typography variant="body2">
          <b>Description:</b> {description}
        </Typography>
        <br />
      </>
    )}
  </>
);

const PluginsSection = ({ plugins }) => (
  <>
    {plugins && plugins.length > 0 && (
      <>
        <Typography variant="body2">
          <b>Plugins required:</b>
        </Typography>
        {plugins.map(plugin => (
          <Typography key={plugin.name} variant="body2" style={{ marginLeft: '2em' }}>
            {plugin.name} {plugin.version}
          </Typography>
        ))}
        <br />
      </>
    )}
  </>
);

const JobActions = ({ jobActions, jobName }) => {
  return (<>
    {Array.isArray(jobActions) && jobActions &&
      jobActions.sort((a, b) => a?.hours_elapsed - b?.hours_elapsed).map((action, index) => (
        <ActionDetails key={`${jobName}-action-${index}`} action={action} jobName={jobName} index={index} />
      ))}
    {!Array.isArray(jobActions) && jobActions &&
      <Typography sx={{ marginLeft: '4em' }} variant="body2">
        <UnderlineSpan title="missing `actions` as a list, prepend with `-`"> actions? </UnderlineSpan>
      </Typography>
    }
    {jobActions === undefined  &&
      <Typography sx={{ marginLeft: '4em' }} variant="body2">
        <UnderlineSpan title="missing `actions` block"> actions? </UnderlineSpan>
      </Typography>
    }
  </>)
};

const JobSection = ({ jobs }) => {
  return (<>
    {jobs && (typeof jobs === 'object') && Object.keys(jobs).length > 0 && (
      <>
        {Object.keys(jobs).map(job => (
          <React.Fragment key={job}>
            <Typography variant="subtitle2" style={{ marginLeft: '2em' }}>
              {job}:
            </Typography>
            <JobActions jobActions={jobs[job]?.actions} jobName={job} />
          </React.Fragment>
        ))}
        <br />
      </>
    )}
    {jobs === undefined  &&
      <Typography sx={{ marginLeft: '2em' }} variant="subtitle2">
        <UnderlineSpan title="missing `jobs` block"> jobs? </UnderlineSpan>
      </Typography>
    }
  </>)
};

const PioreactorSection = ({ pioreactors }) => (
  <>
    {pioreactors && (typeof pioreactors === 'object') &&
      Object.keys(pioreactors).length > 0 &&
      Object.keys(pioreactors).map(pioreactor => (
        <React.Fragment key={pioreactor}>
          <Typography variant="subtitle2">Pioreactor {pioreactor} does:</Typography>
          <Typography variant="body2" style={{ marginLeft: '2em' }}>
            {pioreactors[pioreactor]?.label ? (
              <>Relabel to <span style={highlightedTarget}>{pioreactors[pioreactor].label}</span></>
            ) : (
              <></>
            )}
          </Typography>
          <JobSection jobs={pioreactors[pioreactor]?.jobs} />
          <br />
        </React.Fragment>
      ))}
  </>
);

export const DisplayProfile = ({ data }) => {
  return (
    <Card sx={DisplayProfileCard}>
      <CardContent sx={{ padding: '10px' }}>
        <Box>
          <Typography variant="subtitle2">preview:</Typography>
        </Box>
          <Typography variant="h6">{data.experiment_profile_name || <UnderlineSpan title="missing `experiment_profile_name`">???</UnderlineSpan>}</Typography>
        <Typography sx={{ mb: 1.5 }} variant="subtitle1" color="text.secondary" gutterBottom>
          Created by {data.metadata.author || <UnderlineSpan title="missing `author`">???</UnderlineSpan>}
        </Typography>
        <DescriptionSection description={data.metadata.description} />
        <PluginsSection plugins={data.plugins} />

        {data?.common?.jobs && (Object.keys(data?.common?.jobs).length > 0) && <>
          <Typography variant="subtitle2">All Pioreactor(s) do:</Typography>
          <JobSection jobs={data?.common?.jobs} />
          </>
        }
        <PioreactorSection pioreactors={data.pioreactors} />
      </CardContent>
    </Card>
  );
};


export const DisplayProfileError = ({ error }) => {
  return (
    <Card sx={DisplayProfileCard}>
      <CardContent sx={{padding: "10px"}}>
       <Typography variant="body2">
        <pre>{error}</pre>
       </Typography>
      </CardContent>
    </Card>
  );
};



