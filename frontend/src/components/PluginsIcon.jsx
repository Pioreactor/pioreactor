import React from 'react';
import SvgIcon from '@mui/material/SvgIcon';

function PluginsIcon(props) {
  return (
    <SvgIcon viewBox="0 0 24 24" {...props}>
      <g fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M6 4V3a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-1" />
        <rect x="2" y="6" width="16" height="16" rx="1" />
        <path d="M6 14h8m-4-4v8" />
      </g>
    </SvgIcon>
  );
}

export default PluginsIcon;
