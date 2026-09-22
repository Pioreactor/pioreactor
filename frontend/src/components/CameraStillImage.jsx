import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { applyMagma } from "../utils/magma";

export default function CameraStillImage({ src, alt, loading, magma }) {
  const imageRef = React.useRef(null);
  const canvasRef = React.useRef(null);
  const [transformError, setTransformError] = React.useState(false);

  const draw = React.useCallback(() => {
    const image = imageRef.current;
    const canvas = canvasRef.current;
    if (!magma || !canvas || !image?.complete || !image.naturalWidth) return;

    try {
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0);
      const frame = context.getImageData(0, 0, canvas.width, canvas.height);
      applyMagma(frame.data);
      context.putImageData(frame, 0, 0);
      setTransformError(false);
    } catch (_error) {
      setTransformError(true);
    }
  }, [magma]);

  React.useEffect(() => {
    draw();
  }, [draw, src]);

  return (
    <Box sx={{ position: "relative" }}>
      <Box
        component="img"
        ref={imageRef}
        src={src}
        alt={alt}
        loading={loading}
        onLoad={draw}
        sx={{ display: "block", width: "100%", aspectRatio: "4 / 3", objectFit: "contain" }}
      />
      {magma && (
        <Box
          component="canvas"
          ref={canvasRef}
          aria-hidden="true"
          sx={{
            position: "absolute", inset: 0, width: "100%", height: "100%",
            objectFit: "contain", pointerEvents: "none",
            visibility: transformError ? "hidden" : "visible",
          }}
        />
      )}
      {magma && transformError && (
        <Typography role="alert" variant="caption" color="error">
          Could not apply Magma. Toggle the switch to retry.
        </Typography>
      )}
    </Box>
  );
}
