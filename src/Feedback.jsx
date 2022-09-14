import React from "react";
import Grid from '@mui/material/Grid';
import { makeStyles } from '@mui/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import LoadingButton from '@mui/lab/LoadingButton';
import Box from '@mui/material/Box';
import {Typography} from '@mui/material';
import FormGroup from '@mui/material/FormGroup';
import TextField from '@mui/material/TextField';


const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px",
  },
  title: {
    fontSize: 14,
  },
  cardContent: {
    padding: "10px"
  },
  pos: {
    marginBottom: 0,
  },
  textField:{
    marginTop: theme.spacing(1),
    marginBottom: theme.spacing(1)
  },
  formControl: {
    margin: theme.spacing(3),
  },
  halfTextField: {
    width: "70%"
  },
}));



function FeedbackContainer(props){
  const classes = useStyles();
  const [formError, setFormError] = React.useState(false);
  const [helperText, setHelperText] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [feedback, setFeedback] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [hasBeenSent, setHasBeenSent] = React.useState(false);

  function publishFeedbackToCloud(){
    setSending(true)
    fetch("https://us-central1-pioreactor-backend.cloudfunctions.net/feedback", {
      method:"POST",
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
          email: email,
          message: feedback
          })
      })
    setSending(false)
    setHasBeenSent(true)
  }

  function onSubmit(e) {
    e.preventDefault();
    if (email === ""){
      setFormError(true)
      setHelperText("Can't be blank.")
      return
    }
    publishFeedbackToCloud()
  }

  const onEmailChange = (e) => {
    setFormError(false)
    setHelperText("")
    setEmail(e.target.value)
  }
  const onFeedbackChange = (e) => {
    setFeedback(e.target.value)
  }

  return(
    <React.Fragment>
      <div>
        <Typography variant="h5" component="h2">
          <Box fontWeight="fontWeightBold">
            Share feedback
          </Box>
        </Typography>
      </div>
      <Card className={classes.root}>
        <CardContent className={classes.cardContent}>
        <p>
        Include your email, and we may get back to you with some questions or advice about your provided feedback.
        We appreciate all feedback sent to us!
        </p>
        <FormGroup>
          <Grid container spacing={1}>
            <Grid item xs={12} md={6}>
              <TextField
                error={formError}
                id="email"
                type="email"
                label="Email"
                required
                onChange={onEmailChange}
                className={`${classes.halfTextField} ${classes.textField}`}
                value={email}
                helperText={helperText}
                />
            </Grid>
            <Grid item xs={12} md={12}>
              <TextField
                label="What went wrong? What went right? What are you unsure about?"
                maxRows={4}
                multiline
                required
                onChange={onFeedbackChange}
                value={feedback}
                className={classes.textField}
                minRows={3}
                fullWidth={true}
              />
            </Grid>

            <Grid item xs={12} md={12}>
              <LoadingButton
                loading={sending}
                variant="contained"
                color="primary"
                disabled={hasBeenSent}
                onClick={onSubmit}>
                {hasBeenSent ? "Submitted" : "Submit"}
              </LoadingButton>
            </Grid>
          </Grid>
        </FormGroup>



        </CardContent>
      </Card>
    </React.Fragment>
)}


function Feedback(props) {
    React.useEffect(() => {
      document.title = props.title;
    }, [props.title])
    return (
        <Grid container spacing={3} >
          <Grid item md={12} xs={12}>
            <FeedbackContainer/>
          </Grid>
        </Grid>
    )
}

export default Feedback;

