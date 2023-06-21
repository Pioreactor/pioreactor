import React from 'react'

import { makeStyles } from '@mui/styles';

import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown'
import Button from '@mui/material/Button'
import ButtonGroup from '@mui/material/ButtonGroup'
import Menu from '@mui/material/Menu'

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
      const item = React.cloneElement(child, {
        'aria-selected': selected ? 'true' : undefined,
        onClick: handleItemClick(child.props.value),
        role: 'option',
        selected,
        value: undefined, // The value is most likely not a valid HTML attribute.
        'data-value': child.props.value, // Instead, we provide it as a data attribute.
        'data-value-readable': valueReadable,
      })
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