import React from 'react';
import SvgIcon from '@mui/material/SvgIcon';

// Singular counterpart to PluginsIcon: one module.
function PluginIcon(props) {
  return (
    <SvgIcon viewBox="0 0 24 24" {...props}>
      <g fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="4" width="16" y="4" height="16" rx="1" />
        <path d="M8 12h8m-4-4v8" />
      </g>
    </SvgIcon>
  );
}

export default PluginIcon;
