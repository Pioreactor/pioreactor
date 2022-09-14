import React from 'react'

import clsx from 'clsx';

export default  function UnderlineSpan(props){
  const title = props.title

  return (
    <span className={clsx({underlineSpan: title ? true : false})} title={title}>
      {props.children}
    </span>
 )
}
