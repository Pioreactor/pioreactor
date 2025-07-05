import React from 'react'
import SvgIcon from '@mui/material/SvgIcon'

function PioreactorIcon(props) {
  return (
    <SvgIcon viewBox="-4 -2 24 24" strokeWidth="1.9" {...props}>
      <path
        d="M1.4 18.9L1.4 14.7L0 14.7L0 11.2L2.8 11.2L2.8 0H14v11.2h2.8v3.5h-1.4v4.2H1.4z"
        fill={props.fillColor || 'none'}
        stroke="currentColor"
      />
      <circle
        cx="8.4"
        cy="13.3"
        r="2.1"
        fill={props.fillColor || 'none'}
        stroke="currentColor"
      />
    </SvgIcon>
  )
}

export default PioreactorIcon
