import React from 'react'
import SvgIcon from '@mui/material/SvgIcon'

function CalibrationsIcon(props) {
  const maskId = `calibrations-icon-mask-${React.useId()}`
  return (
    <SvgIcon viewBox="0 0 24 24" {...props}>
      <defs>
        {/* knock the back axes out where they pass behind the front chart */}
        <mask id={maskId}>
          <rect width="24" height="24" fill="#fff" />
          <g fill="#000" stroke="#000" strokeWidth="2.5" strokeLinejoin="round">
            <path d="M2 7h2v13h14v2H2z" />
            <path d="M6.5 17 9.5 13.5 12.5 14.5 16 8.5" fill="none" strokeWidth="6" strokeLinecap="round" />
          </g>
        </mask>
      </defs>
      <path d="M7 2v15h15" fill="none" stroke="currentColor" strokeWidth="2" mask={`url(#${maskId})`} />
      <path d="M2 7h2v13h14v2H2z" />
      <path d="M6.5 17 9.5 13.5 12.5 14.5 16 8.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="6.5" cy="17" r="1.6" />
      <circle cx="9.5" cy="13.5" r="1.6" />
      <circle cx="12.5" cy="14.5" r="1.6" />
      <circle cx="16" cy="8.5" r="1.6" />
    </SvgIcon>
  )
}

export default CalibrationsIcon
