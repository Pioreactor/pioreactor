import React, { useState } from "react";
import { useColorScheme } from "@mui/material/styles";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ContrastOutlinedIcon from '@mui/icons-material/ContrastOutlined';

export default function AppearanceMenu() {
  const { mode, setMode } = useColorScheme();
  const [anchorEl, setAnchorEl] = useState(null);

  return (
    <>
      <Tooltip title="Appearance">
        <IconButton
          color="inherit"
          aria-label="Appearance"
          aria-haspopup="menu"
          aria-controls={anchorEl ? "appearance-menu" : undefined}
          aria-expanded={Boolean(anchorEl)}
          onClick={(event) => setAnchorEl(event.currentTarget)}
          sx={{ width: 44, height: 44 }}
        >
          <ContrastOutlinedIcon  sx={{ fontSize: 18}} />
        </IconButton>
      </Tooltip>
      <Menu
        id="appearance-menu"
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
        slotProps={{ list: { "aria-label": "Appearance" } }}
      >
        {[["light", "Light"], ["dark", "Dark"], ["system", "System"]].map(([value, label]) => (
          <MenuItem
            key={value}
            role="menuitemradio"
            aria-checked={(mode || "light") === value}
            selected={(mode || "light") === value}
            onClick={() => {
              setMode(value);
              setAnchorEl(null);
            }}
          >
            {label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
