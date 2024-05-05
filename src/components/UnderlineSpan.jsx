import React from 'react'

export default  function UnderlineSpan(props){
  const title = props.title

  return (
    <span className={title ? 'underlineSpan' : ''} title={title}>
      {props.children}
    </span>
 )
}
