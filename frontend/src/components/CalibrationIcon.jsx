import React from 'react'
import SvgIcon from '@mui/material/SvgIcon'

function CalibrationIcon(props) {
  return (
    <SvgIcon viewBox="0 0 24 24" {...props}>
      <path d="M3 3h2v16h16v2H3z" />
      <path d="M7.5 16 11 12.5 14.5 13.5 19 5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="7.5" cy="16" r="1.75" />
      <circle cx="11" cy="12.5" r="1.75" />
      <circle cx="14.5" cy="13.5" r="1.75" />
      <circle cx="19" cy="5" r="1.75" />
    </SvgIcon>
  )
}

export default CalibrationIcon
