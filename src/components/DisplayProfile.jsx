import React from "react";
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import Box from '@mui/material/Box';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import UnderlineSpan from "./UnderlineSpan";
import CalculateOutlinedIcon from '@mui/icons-material/CalculateOutlined';
import PioreactorIcon from "./PioreactorIcon"
import PioreactorsIcon from './PioreactorsIcon';
import { Link } from 'react-router-dom';
import ViewTimelineOutlinedIcon from '@mui/icons-material/ViewTimelineOutlined';


const DisplayProfileCard = {
    height: "350px",
    overflow: "auto",
    backgroundColor: "rgb(250,250,250)",
    letterSpacing: "0em",
    margin: "10px 0px 10px 0px",
    position: "relative",
    width: "98%",
    border: "1px solid #ccc",
    borderRadius: "4px",
    boxShadow: "none",
}

const level1 = { ml: '20px', whiteSpace: "nowrap", mt: "4px"}
const level2 = { ml: '40px', whiteSpace: "nowrap", mt: "4px"}
const level3 = { ml: '70px', whiteSpace: "nowrap", mt: "4px"}


const highlight = {
    display: "inline block",
    padding: "2px 2px"
  }

const expression = {
  fontFamily: "monospace",
}


const highlightedIf = highlight

const highlightedActionType = {}
const highlightedLogMessage = {
  borderLeft:  "3px solid #1e1e1e1e",
  padding: "6px 6px",
  paddingLeft: "10px",
  backgroundColor: "#f3f3f3",
}




function isNumeric(v) {
  if (typeof v != "string") return !Number.isNaN(v)
  return !isNaN(v) && // use type coercion to parse the _entirety_ of the string (`parseFloat` alone does not do this)...
         !isNaN(parseFloat(v)) // ...and ensure strings of whitespace fail
}


function displayExpression(string){
  return  <Chip
            size="small"
            sx={{
                marginTop: "0px",
                marginBottom: "3px",
                maxWidth: 'none'
            }}
            icon={<CalculateOutlinedIcon />}
            label={
                <span style={expression}>{String(string).trim()}</span>
            }
          />
}


function displayPioreactor(pioreactorName){
  return  <Chip
            size="small"
            sx={{
                marginTop: "0px",
                marginBottom: "3px",
                maxWidth: 'none'
            }}
            icon={<PioreactorIcon />}
            clickable component={Link} to={"/pioreactors/" + pioreactorName}
            label={pioreactorName}
          />
}


function displayVariable(string){
  return  <Chip size="small" sx={{marginTop: "0px", marginBottom: "3px"}}  label={<span style={expression}>{String(string).trim()}</span>} />
}

function almostExpressionSyntax(string){
    const almostPattern1 = /{+(.*?)}+/;
    const almostPattern2 = /{{(.*?)}}/;

    if (almostPattern1.exec(string) || almostPattern2.exec(string)){
      return true
    }
    return false

}

function processOptionalBracketedExpression(value, missingMessage="Missing expression"){

    if (value === undefined || value === null){
      return <UnderlineSpan title={missingMessage}>??</UnderlineSpan>;
    }

    const pattern = /\${{(.*?)}}/;
    var match = pattern.exec(String(value));

    if (match || almostExpressionSyntax(String(value)) || typeof value === 'object' ) {
      return processBracketedExpression(value)
    } else {
      return displayExpression(value)
    }
}

function extractAndApply(inputString, func) {
    // Regex pattern to find all occurrences of ${ {...} }
    const pattern = /(\${{.*?}})/g;

    // Split the input string into an array of text and placeholders
    const parts = [];
    let lastIndex = 0;

    inputString.replace(pattern, (match, p1, offset) => {
        parts.push(inputString.substring(lastIndex, offset)); // Push text before the match
        parts.push(func(p1)); // Push the React node returned by func
        lastIndex = offset + match.length;
    });

    // Push any remaining text after the last match
    parts.push(inputString.substring(lastIndex));
    return parts;
}


function processBracketedExpression(value) {
    if (value === undefined || value === null || typeof value === 'object'){
      return <UnderlineSpan title="Missing expression">??</UnderlineSpan>;
    }


    const pattern = /\${{(.*?)}}/;
    var match = pattern.exec(String(value));

    if (match) {
      return displayExpression(match[1])
    }

    var almostPattern = /{{(.*?)}}/;
    match = almostPattern.exec(String(value));
    if (match) {
        return <UnderlineSpan title="Missing $ infront: ${{ ... }}">??</UnderlineSpan>
    }

    almostPattern = /{+(.*?)}+/;
    match = almostPattern.exec(String(value));
    if (match) {
        return <UnderlineSpan title="Requires double curly braces: {{  and  }}">??</UnderlineSpan>; // Return the content inside the brackets
    }
    return displayVariable(String(value));
}

const humanReadableDuration = (duration, missingMsg='missing `hours_elapsed` field') => {
  if (duration === undefined || duration === null){
    return <UnderlineSpan title={missingMsg}>after ??</UnderlineSpan>
  }
  else if (!isNumeric(duration)){
    return <UnderlineSpan title={missingMsg}>after ??</UnderlineSpan>
  }
  else if (duration < 0){
    return <UnderlineSpan title={missingMsg}>after ??</UnderlineSpan>
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
    return <UnderlineSpan title={missingMsg}>after ??</UnderlineSpan>
  }
  else if (!isNumeric(duration)){
    return <UnderlineSpan title={missingMsg}>after ??</UnderlineSpan>
  }
  else if (duration < 0){
    return <UnderlineSpan title={missingMsg}>after ??</UnderlineSpan>
  }
  else if (duration === 0){
    return `beginning immediately`
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
  if (action?.if !== undefined && action?.if !== null) {
    if_ = <>
            if {processOptionalBracketedExpression(action.if)} is true,
          </>
  } else {
    if_ = <></>
  }

  const renderOptions = () => {
    if (action?.options && typeof action.options === 'object' && !Array.isArray(action.options)) {
      return Object.keys(action.options).map((option, idx) => {
        const optionValue = action.options[option];
        if (typeof optionValue === 'object') {
          return (
            <Typography key={`option-${idx}`} variant="body2" sx={level3}>
              — set {displayVariable(option)} → <UnderlineSpan title="Requires value or expression ${{..}}">??</UnderlineSpan>
            </Typography>
          ); // intermediate state when typing
        }
        return (
          <Typography key={`option-${idx}`} variant="body2" sx={level3}>
            — set {displayVariable(option)} → {processBracketedExpression(optionValue)}
          </Typography>
        );
      });
    }
    return null;
  };

  const renderConfigOverrides = () => {
    if (action?.config_overrides && typeof action.config_overrides === 'object' && !Array.isArray(action.config_overrides)) {
      return Object.keys(action.config_overrides).map((option, idx) => {
        const optionValue = action.config_overrides[option];
        if (typeof optionValue === 'object') {
          return (
            ""
          ); // intermediate state when typing
        }
        return (
          <Typography key={`option-${idx}`} variant="body2" sx={level3}>
            — set {displayVariable(`[${jobName}.config].${option}`)} → {processBracketedExpression(optionValue)}
          </Typography>
        );
      });
    }
    return null;
  };

  const renderInvalidOptionsMessage = () => {
    if (action?.type === 'update' && action.options === undefined) {
      return (
        <Typography variant="body2" sx={level3}>
          <UnderlineSpan title="missing `options`">options??</UnderlineSpan>
        </Typography>
      );
    }
    if (Array.isArray(action.options)) {
      return (
        <Typography variant="body2" sx={level3}>
          <UnderlineSpan title="`options` field doesn't use `-` in front. Remove it.">invalid options syntax!</UnderlineSpan>
        </Typography>
      );
    }
    return null;
  };

  switch (action?.type) {
    case 'start':
    case 'update':
      return (
        <>
          <Typography variant="body2" sx={level2}>
            {index + 1}. {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)}, {if_} <span style={highlightedActionType}>{action.type}</span> <span style={{ fontWeight: 500 }}>{jobName}</span>
          </Typography>
          {renderOptions()}
          {renderInvalidOptionsMessage()}
          {renderConfigOverrides()}
        </>
      );
    case 'log':
      return (
        <>
          <Typography variant="body2" sx={level2}>
            {index + 1}. {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)}, {if_} <span style={highlightedActionType}>log</span> the message:
          </Typography>
            {action.options?.message &&
            <Typography variant="body2" sx={level3}>
              <span style={highlightedLogMessage}>{extractAndApply(action.options.message, processBracketedExpression)}</span>
            </Typography>
            }
        </>
      );
    case 'stop':
    case 'pause':
    case 'resume':
      return (
        <>
          <Typography variant="body2" sx={level2}>
            {index + 1}. {if_} <span style={highlightedActionType}>{action.type}</span> <span style={{ fontWeight: 500 }}>{jobName}</span> {after(action.hours_elapsed)} {humanReadableDuration(action.hours_elapsed)}
          </Typography>
        </>
      );
    case 'when':
      return (
        <>
          <Typography variant="body2" sx={level2}>
            {index + 1}. {if_} {after(action.hours_elapsed)} {humanReadableDurationPre(action.hours_elapsed, 'missing `hours_elapsed` field')}, the first time <span style={highlightedActionType}>when</span> <span style={highlightedIf}>{processOptionalBracketedExpression(action?.condition, "missing `condition`")}</span>, execute:
          </Typography>
          <Box sx={level1}>
          {Array.isArray(action.actions) && action.actions.sort((a, b) => a?.hours_elapsed - b?.hours_elapsed).map((action, index) => (
            <ActionDetails key={index} action={action} jobName={jobName} index={index} />
          ))}
          </Box>
        </>
      );
    case 'repeat':
      return (
        <>
          <Typography variant="body2" sx={level2}>
            {index + 1}. {if_} {after(action.hours_elapsed)} {humanReadableDurationPre(action.hours_elapsed, 'missing `hours_elapsed` field')}, <span style={highlightedActionType}>repeat</span> the following every {humanReadableDuration(action.repeat_every_hours, 'missing `repeat_every_hours` field')},
          </Typography>
          {action.while && (
            <Typography variant="body2" sx={level3}>
              while <span style={highlightedIf}>{processOptionalBracketedExpression(action.while)}</span> {action.max_hours ? "or" : ""}
            </Typography>
          )}
          {action.max_hours && (
            <Typography variant="body2" sx={level3}>
              until {humanReadableDuration(action.max_hours, 'max_hours')} have passed
            </Typography>
          )}
          <Box sx={level1}>
            {Array.isArray(action.actions) && action.actions.sort((a, b) => a?.hours_elapsed - b?.hours_elapsed).map((action, index) => (
              <ActionDetails key={index} action={action} jobName={jobName} index={index} />
            ))}
          </Box>
          {(action.actions === undefined) &&
            <Typography variant="body2" sx={level3}>
              <UnderlineSpan title="Missing `actions` block">actions??</UnderlineSpan>
            </Typography>
          }
        </>
      );
    default:
      return <>
        <Typography variant="body2" sx={level2}>
        {index + 1}. {if_} <UnderlineSpan title="`type` required: one of {start, stop, pause, resume, log, repeat, when}">??</UnderlineSpan>
        </Typography>
      </>;
  }
};


const DescriptionSection = ({ description, sx }) => (
  <>
    {description &&  (typeof description === 'string' || description instanceof String) && (
      <Box sx={sx}>
        <Typography variant="subtitle2">
        Description:
        </Typography>
        <Typography variant="body2" sx={{whiteSpace: "pre-line"}}>
        {description}
        </Typography>
      </Box>
    )}
  </>
);

const PluginsSection = ({ plugins }) => (
  <>
    {plugins && Array.isArray(plugins) && plugins.length > 0 && (
      <>
        <Typography variant="body2">
          <b>Plugins required:</b>
        </Typography>
        {plugins.map(plugin => (
          <Typography key={plugin?.name} variant="body2" sx={level1}>
            {plugin?.name || <UnderlineSpan title="require `name` key"> name?? </UnderlineSpan>} {plugin?.version || <UnderlineSpan title="require `version` as string"> version?? </UnderlineSpan>}
          </Typography>
        ))}
        <br />
      </>
    )}
    {plugins && !Array.isArray(plugins) && (
      <>
      <Typography variant="body2">
          <b>Plugins required:</b>
      </Typography>
      <Typography sx={level1} variant="body2">
        <UnderlineSpan title="require list, prepend with `-`"> plugins?? </UnderlineSpan>
      </Typography>
      </>
      )
    }
  </>
);

const JobActions = ({ jobActions, jobName }) => {
  return (<>
    {Array.isArray(jobActions) && jobActions &&
      jobActions.sort((a, b) => a?.hours_elapsed - b?.hours_elapsed).map((action, index) => (
        <ActionDetails key={`${jobName}-action-${index}`} action={action} jobName={jobName} index={index} />
      ))}
    {!Array.isArray(jobActions) && jobActions &&
      <Typography sx={level2} variant="body2">
        <UnderlineSpan title="requires `actions` as a list, prepend with `-`"> actions?? </UnderlineSpan>
      </Typography>
    }
    {jobActions === undefined  &&
      <Typography sx={level2} variant="body2">
        <UnderlineSpan title="missing `actions` block"> actions?? </UnderlineSpan>
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
            <Typography variant="subtitle2" sx={level1}>
              {["temperature_control", "dosing_control", "led_control"].includes(job) ? <UnderlineSpan title={`Change to ${job.replace("_control", "")}_automation`}>{job}</UnderlineSpan> : job}:
            </Typography>
            <DescriptionSection sx={{...level2, mb: '10px', mt: '5px' }}  description={jobs[job]?.description}/>
            <JobActions jobActions={jobs[job]?.actions} jobName={job} />
          </React.Fragment>
        ))}
        <br />
      </>
    )}
    {jobs === undefined  &&
      <Typography sx={level1} variant="subtitle2">
        <UnderlineSpan title="missing `jobs` block"> jobs?? </UnderlineSpan>
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
          <Typography variant="subtitle2">Pioreactor {displayPioreactor(pioreactor)} does:</Typography>
          <Typography variant="body2" sx={level1}>
            {pioreactors[pioreactor]?.label ? (
              <>Relabel {displayPioreactor(pioreactor)} → {displayPioreactor(pioreactors[pioreactor].label)}</>
            ) : (
              <></>
            )}
          </Typography>
          <JobSection jobs={pioreactors[pioreactor]?.jobs} />
        </React.Fragment>
      ))}
  </>
);

const AuthorSection = ({ author }) => (
  <>
    {author &&  (typeof author === 'string' || author instanceof String) && (
      <>
        <Typography sx={{ mb: 1.5 }} variant="subtitle1" color="text.secondary" gutterBottom>
          Created by { author || <UnderlineSpan title="missing `author`">??</UnderlineSpan>}
        </Typography>
      </>
    )}
  </>
);

const ParametersSection = ({ parameters }) => (
  <>
    {parameters && Object.keys(parameters).length > 0 && (
      <>
        <Typography  variant="subtitle2">
          Inputs:
        </Typography>
        { (typeof parameters === 'object' )  && Object.entries(parameters).map(([key, value]) => (
          <Typography key={key}  sx={level1} variant="body2" color="text.primary">
            — assign {displayVariable(value)} to parameter {displayExpression(key)}
          </Typography>
        ))}
        <br/>
      </>
    )}
  </>
);


export const DisplayProfile = ({ data }) => {
  return (
    <Card sx={DisplayProfileCard}>
      <CardContent sx={{ padding: '10px' }}>
        <Typography variant="h6"><ViewTimelineOutlinedIcon sx={{verticalAlign: "middle", margin:"0px 3px"}}/>{data?.experiment_profile_name || <UnderlineSpan title="missing `experiment_profile_name`">??</UnderlineSpan>}</Typography>
        <AuthorSection author={data?.metadata?.author} />
        <DescriptionSection description={data?.metadata?.description} />
        <br/>
        <PluginsSection plugins={data?.plugins} />
        <ParametersSection parameters={data?.inputs} />

        {data?.common?.jobs && (Object.keys(data?.common?.jobs).length > 0) && <>
          <Typography variant="subtitle2">All assigned Pioreactors <PioreactorsIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 2px 0px 0px"}} /> do:</Typography>
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
        <pre>Error: {error}</pre>
       </Typography>
      </CardContent>
    </Card>
  );
};



