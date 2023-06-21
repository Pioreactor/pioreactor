import React from "react";
import { makeStyles } from '@mui/styles';
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



const DisplaySourceCode = ({ sourceCode }) => {
  const classes = useStyles();
  return (
    <Card className={classes.DisplayProfileCard}>
      <CardContent className={classes.cardContent}>
        <pre>{sourceCode}
        </pre>
      </CardContent>
    </Card>
  );
};


export default DisplaySourceCode;

