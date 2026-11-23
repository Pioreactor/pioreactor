import { useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import EmptyState from "./EmptyState";
import { uiColors } from "../theme/colors";
import { diffConfigs } from "../utils/configDiff";


const screenReaderOnly = {
  position: "absolute",
  width: 1,
  height: 1,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
};

const insertedSx = {
  backgroundColor: uiColors.changeHighlight,
  color: "text.primary",
  textDecoration: "none",
  borderRadius: "2px",
  boxDecorationBreak: "clone",
  WebkitBoxDecorationBreak: "clone",
};

const deletedSx = {
  color: "text.secondary",
  textDecoration: "line-through",
};


function Inserted({ children }) {
  return (
    <Box component="ins" sx={insertedSx}>
      <Box component="span" sx={screenReaderOnly}>Added: </Box>
      {children}
    </Box>
  );
}


function Deleted({ children }) {
  return (
    <Box component="del" sx={deletedSx}>
      <Box component="span" sx={screenReaderOnly}>Removed: </Box>
      {children}
    </Box>
  );
}


function formatEntry(key, value) {
  return value === null || value === undefined ? key : `${key}=${value}`;
}


function EntryLine({ entry, sectionStatus }) {
  if (sectionStatus === "added" || entry.status === "added") {
    return <Inserted>{formatEntry(entry.key, entry.newValue)}</Inserted>;
  }
  if (sectionStatus === "removed" || entry.status === "removed") {
    return <Deleted>{formatEntry(entry.key, entry.oldValue)}</Deleted>;
  }
  return (
    <>
      {entry.key}=<Inserted>{entry.newValue}</Inserted>{" "}
      <Deleted>{entry.oldValue}</Deleted>
    </>
  );
}


function SectionHeader({ name, status }) {
  const label = `[${name}]`;
  if (status === "added") {
    return <Inserted>{label}</Inserted>;
  }
  if (status === "removed") {
    return <Deleted>{label}</Deleted>;
  }
  return <Box component="span" sx={{ color: "text.secondary" }}>{label}</Box>;
}


export default function ConfigChangeSummary({ savedCode, code }) {
  const changes = useMemo(() => diffConfigs(savedCode, code), [savedCode, code]);

  return (
    <Box component="section" aria-labelledby="config-change-summary-title">
      <Typography id="config-change-summary-title" variant="h6" component="h2" sx={{ mb: 1 }}>
        Unsaved changes
      </Typography>
      {changes.length === 0 ? (
        <EmptyState>Only comments or formatting changed.</EmptyState>
      ) : (
        <Box sx={{ fontFamily: "monospace", fontSize: "14px", lineHeight: 1.7 }}>
          {changes.map((section) => (
            <Box key={section.name} sx={{ mb: 1.5, "&:last-child": { mb: 0 } }}>
              <div><SectionHeader name={section.name} status={section.status} /></div>
              {section.entries.map((entry) => (
                <Box key={entry.key} sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                  <EntryLine entry={entry} sectionStatus={section.status} />
                </Box>
              ))}
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
