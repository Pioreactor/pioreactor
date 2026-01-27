import React from "react";
import CircularProgress from '@mui/material/CircularProgress';
import Button from "@mui/material/Button";
import { lostRed } from "../color";

export default function PatientButton({buttonText, onClick, color, variant, disabled}) {
  const [text, setText] = React.useState(buttonText)
  const [error, setError] = React.useState(null)

  React.useEffect(() => {
    setText(buttonText);
  }, [buttonText]);

  const handleClick = async () => {
    setError(null)
    setText(<CircularProgress color="inherit" size={21}/>);
    try {
      await onClick();
    } catch (error) {
      setError(error.message)
      setTimeout(() => setText(buttonText), 1000); // Reset to original text after a delay
    }
  };

  return (
    <>
    {error && <p style={{color: lostRed}}>{error}</p>}
    <Button
      disableElevation
      sx={{width: "70px", mt: "5px", height: "31px",}}
      color={color}
      variant={variant}
      disabled={disabled}
      size="small"
      onClick={handleClick}
    >
      {text}
    </Button>
    </>
  )
}
