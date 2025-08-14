import React from 'react'
import SvgIcon from '@mui/material/SvgIcon'

function Pioreactor40Icon(props) {
  return (
    <SvgIcon viewBox="-4 0 24 24" strokeWidth="1.9" {...props}>
      <path d="m1.94,22.75l0,-4.2l-1.4,0l0,-3.5l2.8,0l0,-14.05l11.2,0l0,14.05l2.8,0l0,3.5l-1.4,0l0,4.2l-14,0z"
            fill={props.fillColor || 'none'} id="svg_1"
            stroke="currentColor"
      />
      <circle cx="8.94" cy="17.15"
              fill={props.fillColor || 'none'} id="svg_2" r="2.1"
              stroke="currentColor"
      />
    </SvgIcon>
  )
}

export default Pioreactor40Icon
