import React from "react";
import { styled } from '@mui/material/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Editor from 'react-simple-code-editor';
import { highlight, languages } from 'prismjs';
import 'prismjs/components/prism-yaml'; // You can add more languages or change it


const StyledCard = styled(Card)(({ theme }) => ({
  height: "350px",
  overflow: "auto",
  backgroundColor: "rgb(248,248,248)",
  letterSpacing: "0em",
  margin: "10px 0px 10px 0px",
  position: "relative",
  width: "98%",
  border: "1px solid #ccc",
  borderRadius: "4px",
  boxShadow: "none"
}));

const StyledCardContent = styled(CardContent)(({ theme }) => ({
}));



const DisplaySourceCode = ({ sourceCode }) => {
  return (
    <StyledCard>
      <StyledCardContent>
        <Editor
          placeholder="Loading..."
          value={sourceCode}
          onValueChange={(code) => code}
          highlight={(code) => highlight(code, languages.yaml)}
          padding={0}
          className={'readonlyEditor'}
          onFocus={(e) => e.target.select()}
          readOnly={"readonly"}
          style={{
            fontSize: "14px",
            fontFamily: 'monospace',
            borderRadius: "3px",
          }}
        />
      </StyledCardContent>
    </StyledCard>
  );
};


export default DisplaySourceCode;
