import React from 'react'
import SvgIcon from '@mui/material/SvgIcon'

function ControlIcon(props) {
  return (
    <SvgIcon viewBox="0 0 24 24" {...props}>
      <path fillRule="evenodd" d="M4 3h16a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm0 2v14h16V5z" />
      <path d="M6 7v10l6-5zm7 1h5v2h-5zm0 6h5v2h-5z" />
    </SvgIcon>
  )
}

export default ControlIcon
