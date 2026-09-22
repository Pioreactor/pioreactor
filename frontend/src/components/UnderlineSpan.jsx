import React from 'react'
import Box from '@mui/material/Box';
import Tooltip from '@mui/material/Tooltip';


export default  function UnderlineSpan(props){
  const title = props.title

  return (
    <Tooltip
      title={title}
      placement="top-start">
      <Box
        component="span"
        className={title ? 'underlineSpan' : ''}
        tabIndex={title ? 0 : undefined}
        sx={{ '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: '2px' } }}
      >
        {props.children}
      </Box>
    </Tooltip>
 )
}
