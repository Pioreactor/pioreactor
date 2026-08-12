import React from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import CalibrationSessionChart from "./CalibrationSessionChart";


export default function CalibrationSessionStepContent({
  step,
  showLoading,
  loadingImages,
  loadingImageIndex,
  loadedStepImageSrc,
  imageActionPending,
  onStepImageLoad,
  onStepImageError,
}) {
  const [enlargedImage, setEnlargedImage] = React.useState(null);

  if (!step) {
    return null;
  }

  const chart = step.metadata?.chart;
  const table = step.metadata?.table;
  const stepImage = step.metadata?.image;
  const guidance =
    typeof step.metadata?.guidance?.message === "string" ? step.metadata.guidance : null;
  const guidanceImage = typeof guidance?.image?.src === "string" ? guidance.image : null;
  const displayedLoadingImage =
    showLoading && loadingImages.length > 0 ? loadingImages[loadingImageIndex] : null;
  const displayedImage = displayedLoadingImage || stepImage;
  const stepImageCanBeEnlarged =
    !displayedLoadingImage && stepImage?.enlargeable === true;
  const stepImageIsLoading =
    !displayedLoadingImage && Boolean(stepImage?.src) && loadedStepImageSrc !== stepImage.src;
  const showImageLoading =
    !displayedLoadingImage && (imageActionPending || stepImageIsLoading);
  const hideDataWhileLoading = showLoading && loadingImages.length > 0;
  const tableColumns = Array.isArray(table?.columns) ? table.columns : [];
  const tableRows = Array.isArray(table?.rows) ? table.rows : [];
  const tableTitle = typeof table?.title === "string" ? table.title : "";
  const tableEmptyMessage =
    typeof table?.empty_message === "string" ? table.empty_message : "No entries yet.";
  const displayedImageElement = displayedImage ? (
    <Box
      component="img"
      src={displayedImage.src}
      alt={displayedImage.alt || ""}
      decoding="async"
      onLoad={() => {
        if (!displayedLoadingImage && stepImage?.src) {
          onStepImageLoad(stepImage.src);
        }
      }}
      onError={() => {
        if (!displayedLoadingImage && stepImage?.src) {
          onStepImageError(stepImage.src);
        }
      }}
      sx={{
        width: "100%",
        maxHeight: displayedImage.max_height || 220,
        aspectRatio: displayedImage.aspect_ratio || "auto",
        display: "block",
        objectFit: "contain",
      }}
    />
  ) : null;

  return (
    <>
      <Box sx={{ mb: 1.5 }}>
        <Typography variant="subtitle1" component="h2">
          {step.title || "Calibration step"}
        </Typography>
      </Box>
      {displayedImage && (
        <Box
          sx={{
            width: "100%",
            borderRadius: 1,
            backgroundColor: "action.hover",
          }}
        >
          {stepImageCanBeEnlarged ? (
            <Box
              component="button"
              type="button"
              aria-label={`Enlarge image: ${stepImage.caption || stepImage.alt || "Calibration step image"}`}
              onClick={() => setEnlargedImage(stepImage)}
              sx={{
                display: "block",
                width: "100%",
                p: 0,
                border: 0,
                backgroundColor: "transparent",
                cursor: "zoom-in",
                "&:focus-visible": {
                  outline: "2px solid",
                  outlineColor: "primary.main",
                  outlineOffset: "-2px",
                },
              }}
            >
              {displayedImageElement}
            </Box>
          ) : (
            displayedImageElement
          )}
          {displayedImage.caption && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ textAlign: "center", display: "block", width: "100%" }}
            >
              {displayedImage.caption}
            </Typography>
          )}
        </Box>
      )}
      {!displayedLoadingImage && stepImage && (
        <Box
          aria-live="polite"
          aria-busy={showImageLoading}
          sx={{
            minHeight: 32,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 1,
          }}
        >
          {showImageLoading && (
            <>
              <CircularProgress size={20} />
              <Typography variant="body2" color="text.secondary">
                Loading image…
              </Typography>
            </>
          )}
        </Box>
      )}
      {guidance && (
        <Box
          aria-live="polite"
          sx={{
            minHeight: 64,
            display: "flex",
            flexDirection: { xs: "column", sm: "row" },
            alignItems: "center",
            gap: 1.5,
            px: 1.5,
            py: 1,
            borderRadius: 1,
            backgroundColor: "action.hover",
          }}
        >
          {guidanceImage && (
            <Box
              component="img"
              src={guidanceImage.src}
              alt={guidanceImage.alt || ""}
              decoding="async"
              sx={{
                width: { xs: "100%", sm: 280 },
                maxWidth: "100%",
                maxHeight: 120,
                objectFit: "contain",
                flexShrink: 0,
              }}
            />
          )}
          <Box sx={{ minWidth: 0 }}>
            {guidance.title && <Typography variant="subtitle2">{guidance.title}</Typography>}
            <Typography variant="body2" color="text.secondary">
              {guidance.message}
            </Typography>
          </Box>
        </Box>
      )}
      {chart && !hideDataWhileLoading && <CalibrationSessionChart chart={chart} />}
      {table && !hideDataWhileLoading && (
        <Box sx={{ width: "70%", mx: "auto", mt: 2, mb: 4 }}>
          {tableTitle && (
            <Typography variant="subtitle2" color="text.secondary">
              {tableTitle}
            </Typography>
          )}
          {tableRows.length > 0 ? (
            <Table size="small" sx={{ "& th, & td": { px: 1 } }}>
              {tableColumns.length > 0 && (
                <TableHead>
                  <TableRow>
                    {tableColumns.map((column, index) => (
                      <TableCell
                        key={`${column}-${index}`}
                        align={index === 0 ? "left" : "right"}
                      >
                        {column}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
              )}
              <TableBody>
                {tableRows.map((row, rowIndex) => {
                  const cells = Array.isArray(row) ? row : Object.values(row || {});
                  return (
                    <TableRow key={`row-${rowIndex}`}>
                      {cells.map((cell, cellIndex) => (
                        <TableCell
                          key={`cell-${rowIndex}-${cellIndex}`}
                          align={cellIndex === 0 ? "left" : "right"}
                        >
                          {cell}
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ) : (
            <Typography variant="caption" color="text.secondary">
              {tableEmptyMessage}
            </Typography>
          )}
        </Box>
      )}
      {step.body && (
        <Typography variant="body2" sx={{ whiteSpace: "pre-line" }}>
          {step.body}
        </Typography>
      )}
      <Dialog
        open={Boolean(enlargedImage)}
        onClose={() => setEnlargedImage(null)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle sx={{ pr: 6 }}>
          {enlargedImage?.caption || step.title || "Calibration step image"}
          <IconButton
            aria-label="Close"
            onClick={() => setEnlargedImage(null)}
            sx={{ position: "absolute", right: 8, top: 8 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          {enlargedImage && (
            <Box sx={{ backgroundColor: "action.hover", borderRadius: 1, overflow: "hidden" }}>
              <Box
                component="img"
                src={enlargedImage.src}
                alt={enlargedImage.alt || ""}
                decoding="async"
                sx={{
                  display: "block",
                  width: "100%",
                  aspectRatio: enlargedImage.aspect_ratio || "auto",
                  objectFit: "contain",
                }}
              />
            </Box>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
