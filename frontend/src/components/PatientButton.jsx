import React from "react";
import CircularProgress from '@mui/material/CircularProgress';
import Button from "@mui/material/Button";
import { lostRed } from "../color";

export default function PatientButton({buttonText, onClick, color, variant, disabled}) {
  const [error, setError] = React.useState(null)
  const [isPending, setIsPending] = React.useState(false)

  React.useEffect(() => {
    setError(null);
    setIsPending(false);
  }, [buttonText]);

  const buttonContent = isPending
    ? <CircularProgress color="inherit" size={21}/>
    : error
      ? "Retry"
      : buttonText;

  const handleClick = async () => {
    if (!onClick || isPending) {
      return;
    }
    setError(null)
    setIsPending(true);
    try {
      await onClick();
    } catch (error) {
      setError(error?.message || "Something went wrong.")
      setIsPending(false);
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
      disabled={disabled || isPending}
      size="small"
      onClick={handleClick}
    >
      {buttonContent}
    </Button>
    </>
  )
}
