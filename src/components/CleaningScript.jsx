import React from 'react';
import { makeStyles } from '@mui/styles';
import Stepper from '@mui/material/Stepper';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import StepContent from '@mui/material/StepContent';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';

const useStyles = makeStyles((theme) => ({
  root: {
    width: '100%',
  },
  button: {
    marginTop: theme.spacing(1),
    marginRight: theme.spacing(1),
  },
  actionsContainer: {
    marginBottom: theme.spacing(2),
  },
  resetContainer: {
    padding: theme.spacing(3),
  },
  divInstructions: {
    marginBottom: theme.spacing(3),
  }
}));



function CycleLiquid(props) {
  const classes = useStyles();
  const liquid = props.liquid
  const [isClicked, setIsClicked] = React.useState(false)

  const onSubmit = () => {
    fetch("/api/run/remove_waste/$broadcast", {
        method: "POST",
        body: JSON.stringify({duration: 90, duty_cycle: 100}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
    });
    fetch("/api/run/add_media/$broadcast", {
        method: "POST",
        body: JSON.stringify({duration: 50, duty_cycle: 55}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
    });
    fetch("/api/run/add_alt_media/$broadcast", {
        method: "POST",
        body: JSON.stringify({duration: 50, duty_cycle: 55}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
    });
    setIsClicked(true)
  }

  return (
    <div className={classes.divInstructions}>
      <p>{props.additionalMsg}</p>
      <p>Add <b>{liquid}</b> to the non-waste containers. We will cycle this solution through our system. Click the button below once the {liquid} is in place.</p>
      <Button className={classes.button} variant="contained" color={isClicked ? "default" : "primary" } onClick={onSubmit}>Cycle {liquid}</Button>
    </div>
    )
}


function MediaFlush(props) {
  const classes = useStyles();
  const isAlt = props.altMedia
  const [isClicked, setIsClicked] = React.useState(false)

  const onSubmit = () => {
    fetch("/api/run/remove_waste/$broadcast", {
        method: "POST",
        body: JSON.stringify({duration: 90, duty_cycle: 100}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
    })
    if (isAlt){
      fetch("/api/run/add_alt_media/$broadcast", {
        method: "POST",
        body: JSON.stringify({duration: 50, duty_cycle: 66}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
    })
    } else {
      fetch("/api/run/add_media/$broadcast", {
        method: "POST",
        body: JSON.stringify({duration: 50, duty_cycle: 55}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
    })
    }
    setIsClicked(true)
  }

  return (
    <div className={classes.divInstructions}>
      <p>Next, we will prime the {isAlt ? "alt-" : ""}media tubes with our {isAlt ? "alt-" : ""}media.</p>
      <p>Replace the container attached to the {isAlt ? "alt-" : ""}media outflow tubes with the sterlized {isAlt ? "alt-" : ""}media container. Remember to use proper sanitation techniques!</p>
      <Button className={classes.button} variant="contained" color={isClicked ? "default" : "primary" } onClick={onSubmit}>Run {isAlt ? "alt-" : ""}media and waste pumps</Button>
    </div>
    )
}

function AddFinalVolumeOfMedia(props) {
  const classes = useStyles();
  const [isClicked, setIsClicked] = React.useState(false)


  const onSubmit = () => {
    fetch("/api/run/add_media/$broadcast", {
        method: "POST",
        body: JSON.stringify({ml: 12}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
    });
    setIsClicked(true)
  }

  return (
    <div className={classes.divInstructions}>
      <p> Finally, we will add fresh media to our vials </p>
      <Button className={classes.button} variant="contained" color={isClicked ? "default" : "primary" } onClick={onSubmit}>Add 12mL of media</Button>
    </div>
    )
}


function getSteps() {
  return [
    'Setup inflow and outflow tubes',
    '10% bleach cycling',
    '70% alcohol cycling',
    'Distilled water cycling',
    'Media preparation',
    'Alt media preparation',
    'Replace vials',
    'Add initial media to vials'];
}


function getStepContent(step) {
  switch (step) {
    case 0:
      return `For each pioreactor unit, connect the media inflow, alt-media inflow, and waste out flow tubes to an empty
      vial with hat. Connect the all the media outflow tubes to a single empty container, all the alt-media outflow tubes to a single empty container, and
      all the waste inflow tubes to a single, empty, large container.`;
    case 1:
      return <CycleLiquid liquid={"10% bleach solution"}/>;
    case 2:
      return <CycleLiquid additionalMsg={"Remove any excess bleach from the containers, and empty the waste container. Bleach and alcohol should not mix."} liquid={"70% alcohol"}/>;
    case 3:
      return <CycleLiquid liquid={"distilled water"}/>;
    case 4:
      return <MediaFlush />;
    case 5:
      return <MediaFlush altMedia={true}/>;
    case 6:
      return `Using proper sanitation techniques, replace the pioreactor vials - now full of water and media - with the empty-but-innocculated vials`;
    case 7:
      return <AddFinalVolumeOfMedia/>;
    default:
      return 'Unknown step';
  }
}

export default function VerticalLinearStepper() {
  const classes = useStyles();
  const [activeStep, setActiveStep] = React.useState(0);
  const steps = getSteps();

  const handleNext = () => {
    setActiveStep((prevActiveStep) => prevActiveStep + 1);
  };

  const handleBack = () => {
    setActiveStep((prevActiveStep) => prevActiveStep - 1);
  };

  const handleReset = () => {
    setActiveStep(0);
  };

  return (
    <div className={classes.root}>
      <Stepper activeStep={activeStep} orientation="vertical">
        {steps.map((label, index) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
            <StepContent>
              <Typography>{getStepContent(index)}</Typography>
              <div className={classes.actionsContainer}>
                  <Button
                    disabled={activeStep === 0}
                    onClick={handleBack}
                    className={classes.button}
                  >
                    Back
                  </Button>
                  <Button
                    variant="contained"
                    onClick={handleNext}
                    className={classes.button}
                  >
                    {activeStep === steps.length - 1 ? 'Finish' : 'Next'}
                  </Button>
              </div>
            </StepContent>
          </Step>
        ))}
      </Stepper>
      {activeStep === steps.length && (
        <Paper square elevation={0} className={classes.resetContainer}>
          <Typography>All cleaning and preparation steps completed!</Typography>
          <Button onClick={handleReset} className={classes.button}>
            Reset
          </Button>
        </Paper>
      )}
    </div>
  );
}