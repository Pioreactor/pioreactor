import React from "react";
import { styled } from '@mui/material/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';

const StyledCard = styled(Card)(({ theme }) => ({
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
}));

const StyledCardContent = styled(CardContent)(({ theme }) => ({
  padding: "10px",
}));



const DisplaySourceCode = ({ sourceCode }) => {
  return (
    <StyledCard>
      <StyledCardContent>
        <pre style={{whiteSpace: "pre-wrap"}}>
          {sourceCode}
        </pre>
      </StyledCardContent>
    </StyledCard>
  );
};


export default DisplaySourceCode;

