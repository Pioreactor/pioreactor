import React from 'react';
import SvgIcon from '@mui/material/SvgIcon';

// Singular counterpart to PluginsIcon: one module, with connector pins so it doesn't read as an "add" box.
function PluginIcon(props) {
  return (
    <SvgIcon viewBox="0 0 24 24" {...props}>
      <g fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="6" y="3" width="16" height="18" rx="1" />
        <path d="M10 12h8m-4-4v8" />
      </g>
    </SvgIcon>
  );
}

export default PluginIcon;
