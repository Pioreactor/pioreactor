import React from 'react'
import Tooltip from '@mui/material/Tooltip';


export default  function UnderlineSpan(props){
  const title = props.title

  return (
    <Tooltip
      title={title}
      placement="top-start">
      <span className={title ? 'underlineSpan' : ''} >
        {props.children}
      </span>
    </Tooltip>
 )
}
