import React from "react";
import SnackbarContent from "@mui/material/SnackbarContent";
import { useSnackbar } from "notistack";

function getComparableMessage(message) {
  if (typeof message === "string" || typeof message === "number") {
    return String(message);
  }
  return null;
}

export default function Snackbar({
  open = false,
  message,
  children,
  onClose,
  ...options
}) {
  const { enqueueSnackbar, closeSnackbar } = useSnackbar();
  const { style, ...enqueueOptions } = options;
  const activeSnackbarKeyRef = React.useRef(null);
  const closedByChildHandlerKeysRef = React.useRef(new Set());
  const wasOpenRef = React.useRef(false);
  const lastComparableMessageRef = React.useRef(null);

  React.useEffect(() => {
    if (!open) {
      wasOpenRef.current = false;
      lastComparableMessageRef.current = null;

      if (activeSnackbarKeyRef.current !== null) {
        closeSnackbar(activeSnackbarKeyRef.current);
        activeSnackbarKeyRef.current = null;
      }

      return;
    }

    const comparableMessage = getComparableMessage(message);
    const shouldEnqueue =
      !wasOpenRef.current ||
      (comparableMessage !== null && comparableMessage !== lastComparableMessageRef.current);

    if (!shouldEnqueue) {
      return;
    }

    const content = children ?? message;
    if (content === undefined || content === null) {
      return;
    }

    const snackbarKey = enqueueSnackbar(message ?? "", {
      ...enqueueOptions,
      content: (_key, snackMessage) => {
        if (children) {
          let renderedChildren = children;

          if (React.isValidElement(children) && typeof children.props?.onClose === "function") {
            const originalChildOnClose = children.props.onClose;
            renderedChildren = React.cloneElement(children, {
              onClose: (...args) => {
                closedByChildHandlerKeysRef.current.add(_key);
                closeSnackbar(_key);
                originalChildOnClose(...args);
              },
            });
          }

          // notistack transition needs a ref-able root element (fragments can't receive refs)
          return <div style={style}>{renderedChildren}</div>;
        }

        return <SnackbarContent message={snackMessage} style={style} />;
      },
      onClose: (event, reason, key) => {
        const closedByChildHandler = closedByChildHandlerKeysRef.current.has(key);
        if (closedByChildHandler) {
          closedByChildHandlerKeysRef.current.delete(key);
        }

        if (key === activeSnackbarKeyRef.current) {
          activeSnackbarKeyRef.current = null;
          if (!closedByChildHandler) {
            onClose?.(event, reason, key);
          }
        }
      },
    });

    activeSnackbarKeyRef.current = snackbarKey;
    wasOpenRef.current = true;
    lastComparableMessageRef.current = comparableMessage;
  }, [children, closeSnackbar, enqueueOptions, enqueueSnackbar, message, onClose, open, style]);

  React.useEffect(() => {
    return () => {
      if (activeSnackbarKeyRef.current !== null) {
        closeSnackbar(activeSnackbarKeyRef.current);
      }
    };
  }, [closeSnackbar]);

  return null;
}
