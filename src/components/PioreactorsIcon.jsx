import React from 'react'
import SvgIcon from '@mui/material/SvgIcon'

function PioreactorsIcon(props) {
  return (
    <SvgIcon viewBox="0 0 19 19" {...props}>
      {/* Rear Pioreactor */}
      <path
        d="M13 1h3l0.5 8 1.5 0.5-1 6-4 0.5V1Z"
        fill={props.fillColor || 'none'}
      />
      <mask id="rearMask" maskUnits="userSpaceOnUse" x="4" y="0" width="15" height="17" fill="black">
        <rect fill="white" x="4" width="15" height="17" />
        <path
          fillRule="evenodd"
          clipRule="evenodd"
          d="
            M7.89 2h3.77h3.77v7.70h1.88v2.41h-0.94v2.89h-0.94v0.00H7.89v0.00H6.94v-2.89H6v-2.41h1.89V2Z
          "
        />
      </mask>
      <path
        d="
          M7.89 2V0.50H6.39V2h1.50ZM15.43 2h1.50V0.50H15.43V2ZM15.43 9.70h-1.50v1.50h1.50V9.70ZM17.31 9.70h1.50V8.20h-1.50v1.50ZM17.31 12.11v1.50h1.50v-1.50h-1.50ZM16.37 12.11v-1.50h-1.50v1.50h1.50ZM16.37 15v1.50h1.50V15h-1.50ZM15.43 15v-1.50h-1.50V15h1.50ZM15.43 15.00v1.50h1.50v-1.50h-1.50ZM7.89 15h-1.50v1.50h1.50V15ZM7.89 15.00h1.50v-1.50H7.89v1.50ZM6.94 15h-1.50v1.50h1.50V15ZM6.94 12.11h1.50v-1.50H6.94v1.50ZM6 12.11H4.50v1.50H6v-1.50ZM6 9.70V8.20H4.50v1.50H6ZM7.89 9.70v1.50h1.50V9.70H7.89ZM11.66 0.50H7.89v3h3.77v-3ZM15.43 0.50H11.66v3h3.77v-3ZM16.93 9.70V2h-3v7.70h3ZM17.31 8.20H15.43v3h1.88v-3ZM18.81 12.11v-2.41h-3v2.41h3ZM16.37 13.61h0.94v-3h-0.94v3ZM14.87 12.11v2.89h3v-2.89h-3ZM16.37 13.50h-0.94v3h0.94v-3ZM16.93 15v-0.00h-3v0h3ZM7.89 16.50h7.54v-3h-7.54v3ZM6.39 15h3v0h-3v0ZM6.94 16.50h0.94v-3h-0.94v3ZM5.44 12.11v2.89h3v-2.89h-3ZM6 13.61h0.94v-3H6v3ZM4.50 9.70v2.41h3v-2.41h-3ZM7.89 8.20H6v3h1.89v-3ZM6.39 2v7.70h3V2h-3Z
        "
        fill="currentColor"
        mask="url(#rearMask)"
      />

      {/* Front Pioreactor */}
      <rect x="4" y="3" width="9" height="13" fill="white" />
      <mask id="frontMask" maskUnits="userSpaceOnUse" x="0" y="1" width="15" height="17" fill="black">
        <rect fill="white" y="1" width="15" height="17" />
        <path
          fillRule="evenodd"
          clipRule="evenodd"
          d="
            M3.89 3h3.77h3.77v7.70h1.88v2.41h-0.94v2.89h-0.94v0H3.89v0H2.94v-2.89H2v-2.41h1.89V3Z
          "
        />
      </mask>
      <path
        d="
          M3.89 3V1.50H2.39V3H3.89ZM11.43 3h1.50V1.50H11.43V3ZM11.43 10.70H9.93v1.50h1.50v-1.50ZM13.31 10.70h1.50V9.20h-1.50v1.50ZM13.31 13.11v1.50h1.50v-1.50h-1.50ZM12.37 13.11v-1.50h-1.50v1.50h1.50ZM12.37 16v1.50h1.50V16h-1.50ZM11.43 16v-1.50H9.93V16h1.50ZM11.43 16v1.50h1.50V16h-1.50ZM3.89 16H2.39v1.50H3.89V16ZM3.89 16v-1.50H5.39V16H3.89ZM2.94 16H1.44v1.50h1.50V16ZM2.94 13.11H4.44v-1.50H2.94v1.50ZM2 13.11H0.50v1.50H2v-1.50ZM2 10.70V9.20H0.50v1.50H2ZM3.89 10.70v1.50H5.39v-1.50H3.89ZM7.66 1.50H3.89v3h3.77v-3ZM11.43 1.50H7.66v3h3.77v-3ZM12.93 10.70V3H9.93v7.70h3ZM13.31 9.20H11.43v3h1.88v-3ZM14.81 13.11v-2.41h-3v2.41h3ZM12.37 14.61h0.94v-3h-0.94v3ZM10.87 13.11v2.89h3v-2.89h-3ZM12.37 14.50h-0.94v3h0.94v-3ZM12.93 16v-0.00H9.93v0h3ZM3.89 17.50h7.54v-3H3.89v3ZM2.39 16v0h3v0h-3ZM2.94 17.50h0.94v-3h-0.94v3ZM1.44 13.11v2.89h3v-2.89h-3ZM2 14.61h0.94v-3H2v3ZM0.50 10.70v2.41h3v-2.41h-3ZM3.89 9.20H2v3h1.89v-3ZM2.39 3v7.70h3V3h-3Z
        "
        fill="currentColor"
        mask="url(#frontMask)"
      />

      {/* Circular detail */}
      <circle
        cx="7.78"
        cy="12.15"
        r="1.80"
        fill={props.fillColor || 'none'}
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </SvgIcon>
  )
}

export default PioreactorsIcon
