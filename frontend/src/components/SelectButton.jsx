import React from 'react';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import Button from '@mui/material/Button';
import ButtonGroup from '@mui/material/ButtonGroup';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import CheckIcon from '@mui/icons-material/Check';
import Icon from '@mui/material/Icon';

const SelectButton = React.forwardRef((props, ref) => {
  const { textPrefix, onChange = () => {}, onClick = () => {}, value: initialValue, children, buttonStyle, disabled, endIcon } = props;
  const anchorRef = React.useRef(null);
  const [isOpen, setOpen] = React.useState(false);
  const valueRef = React.useRef(initialValue);

  React.useEffect(() => {
    valueRef.current = initialValue;
  }, [initialValue]);

  const handleItemClick = (value) => (e) => {
    setOpen(false);
    Object.defineProperty(e, 'target', { writable: true, value: { value } });
    valueRef.current = value;
    onChange(e);
  };

  const handleButtonClick = (e) => {
    console.log(e)
    const value = valueRef.current;
    Object.defineProperty(e, 'target', { writable: true, value: { value } });
    onClick(e);
  };

  const items = React.Children
    .map(children, child => {
      if (!child) {
        return null;
      }
      const selected = valueRef.current === child.props.value;
      const valueReadable = child.props.children;
      const icon = selected ? <CheckIcon sx={{ marginRight: "5px", verticalAlign: "-1px" }} /> : <Icon sx={{ marginRight: "5px", verticalAlign: "-1px" }} />;
      return (
        <MenuItem
          onClick={handleItemClick(child.props.value)}
          selected={selected}
          role="option"
          aria-selected={selected ? 'true' : undefined}
          data-value-readable={valueReadable}
          data-value={child.props.value}
          value={undefined}
          disabled={child.props.disabled || false}
        >
          {icon}{valueReadable}
        </MenuItem>
      );
    })
    .filter(item => item !== null);

  const displayName = (value) => {
    const foundItem = items.find(item => item.props['data-value'] === value);
    if (!foundItem) {
      // Return fallback text or an empty string
      return 'Loading...';
    }
    return foundItem.props['data-value-readable'];
  };

  return <>
    <ButtonGroup variant='contained' ref={anchorRef}>
      <Button
        onClick={handleButtonClick}
        endIcon={endIcon}
        disabled={disabled}
        sx={{
          ...buttonStyle,
          textTransform: 'none',
          ':last-child': {
            borderTopLeftRadius: 0,
            borderBottomLeftRadius: 0
          }
        }}
      >
        {textPrefix}{displayName(valueRef.current)}
      </Button>
      <Button
        size='small'
        onClick={() => setOpen(true)}
        disabled={disabled}
        role="button"
        sx={{
          textTransform: 'none',
          p: 0,
          minWidth: 32,
          ':first-of-type': {
            borderTopRightRadius: 0,
            borderBottomRightRadius: 0
          }
        }}
      >
        <ArrowDropDownIcon />
      </Button>
    </ButtonGroup>
    <Menu
      open={isOpen}
      onClose={() => setOpen(false)}
      getContentAnchorEl={null}
      anchorEl={anchorRef.current}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      transformOrigin={{ vertical: 'top', horizontal: 'right' }}
    >
      {items}
    </Menu>
  </>;
});

SelectButton.displayName = 'SelectButton';

export default SelectButton;
