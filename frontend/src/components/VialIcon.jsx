import React from 'react'
import SvgIcon from '@mui/material/SvgIcon'

function VialIcon(props) {
  return (
    <SvgIcon viewBox="-1 -2 13 23" strokeWidth="1.9" {...props}>
      <rect
        x="0.56"
        y="0.59"
        width="10.21"
        height="2.72"
        fill="currentColor"
        stroke="currentColor"
        strokeLinejoin="round"
      />
      <path
        d="M0.17 5.96L0.14 19.44H11.17V5.81L0.18 5.97Z"
        fill={props.fillColor || 'none'}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <line fill={props.fillColor || 'none'} id="svg_15" stroke="currentColor" strokeLinejoin="round" x1="7.14" x2="7.14" y1="-1.00" y2="12.94"/>
      <line fill={props.fillColor || 'none'} id="svg_15" stroke="currentColor" strokeLinejoin="round" x1="4" x2="4" y1="0.00" y2="14.94"/>
    </SvgIcon>
  )
}

export default VialIcon
