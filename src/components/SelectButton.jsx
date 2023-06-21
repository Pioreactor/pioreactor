import React from 'react'

import { makeStyles } from '@mui/styles';

import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown'
import Button from '@mui/material/Button'
import ButtonGroup from '@mui/material/ButtonGroup'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import CheckIcon from '@mui/icons-material/Check';
import Icon from '@mui/material/Icon';

const useStyles = makeStyles({
  button: props => (props.buttonStyle),
  buttonDropdown: {},
})

const SelectButton = React.forwardRef((
  props,
  ref,
) => {
  const { textPrefix, onChange = () => {}, onClick = () => {}, value: initialValue, children } = props
  const classes = useStyles(props)
  const anchorRef = (ref || React.useRef(null))
  const [isOpen, setOpen] = React.useState(false)
  const valueRef = React.useRef(initialValue)
  valueRef.current = initialValue

  const handleItemClick = (value) => (e) => {
    setOpen(false)
    Object.defineProperty(e, 'target', { writable: true, value: { value } })
    valueRef.current = value
    onChange(e)
  }

  const handleButtonClick = (e) => {
    const value = valueRef.current
    Object.defineProperty(e, 'target', { writable: true, value: { value } })
    valueRef.current = value
    onClick(e)
  }

  const items = React.Children
    .map(children, child => {
      if (!child) {
        return null
      }
      const selected = valueRef.current === child.props.value
      const valueReadable = child.props.children
      const icon = selected ? <CheckIcon style={{marginRight: "5px", verticalAlign: "-1px"}}/>: <Icon style={{marginRight: "5px", verticalAlign: "-1px"}}/>
      const item = (
        <MenuItem
          onClick={handleItemClick(child.props.value)}
          selected={selected}
          role="option"
          aria-selected={selected ? 'true' : undefined}
          data-value-readable={valueReadable}
          data-value={child.props.value}
          value={undefined}
        >
          {icon}{valueReadable}
        </MenuItem>
      )
      return item
    })
    .filter(item => item !== null)

  const displayName = (value) =>
    (items.find(item => item.props['data-value'] === value)).props['data-value-readable']

  return <>
    <ButtonGroup variant='contained' ref={anchorRef}>
      <Button
        className={classes.button}
        onClick={handleButtonClick}
        endIcon={props.endIcon}
        disabled={props.disabled}
      >
        { textPrefix }{ displayName(valueRef.current) }
      </Button>
      <Button
        className={classes.buttonDropdown}
        size='small'
        onClick={() => setOpen(true)}
        disabled={props.disabled}
      >
        <ArrowDropDownIcon />
      </Button>
    </ButtonGroup>
    <Menu
      open={isOpen}
      onClose={() => setOpen(false)}
      getContentAnchorEl={null} // needed for anchorOrigin to work
      anchorEl={anchorRef.current}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      transformOrigin={{ vertical: 'top', horizontal: 'right' }}
    >
      { items }
    </Menu>
  </>
})

SelectButton.displayName = 'SelectButton'

export default SelectButton