import React from 'react'
import SvgIcon from '@mui/material/SvgIcon'

function EstimatorIcon(props) {
  return (
    <SvgIcon viewBox="0 0 24 24" {...props}>
      <path d="M3 3h2v16h16v2H3z" />
      <path d="M7 16C14 16 18 13 20 4" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="8.5" cy="12" r="1.5" />
      <circle cx="14" cy="8.5" r="1.5" />
      <circle cx="19" cy="14" r="1.5" />
    </SvgIcon>
  )
}

export default EstimatorIcon
