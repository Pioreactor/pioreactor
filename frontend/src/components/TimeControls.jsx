import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';

export function TimeFormatSwitch({ timeScale, setTimeScale }) {
  const onChange = (_, newAlignment) => {
    if (newAlignment !== null) {
      setTimeScale(newAlignment);
      localStorage.setItem('timeScale', newAlignment);
    }
  };

  return (
    <ToggleButtonGroup
      color="primary"
      value={timeScale}
      exclusive
      onChange={onChange}
      size="small"
    >
      <ToggleButton style={{ textTransform: "None" }} value="hours">Elapsed time</ToggleButton>
      <ToggleButton style={{ textTransform: "None" }} value="clock_time">Timestamp</ToggleButton>
    </ToggleButtonGroup>
  );
}

export function TimeWindowSwitch({ timeWindow, setTimeWindow }) {
  const onChange = (_, newAlignment) => {
    if (newAlignment !== null) {
      setTimeWindow(newAlignment);
      localStorage.setItem('timeWindow', newAlignment.toString());
    }
  };

  return (
    <ToggleButtonGroup
      color="primary"
      value={timeWindow}
      exclusive
      onChange={onChange}
      size="small"
    >
      <ToggleButton style={{ textTransform: "None" }} value={1000000}>All time</ToggleButton>
      <ToggleButton style={{ textTransform: "None" }} value={12}>Past 12h</ToggleButton>
      <ToggleButton style={{ textTransform: "None" }} value={1}>Past hour</ToggleButton>
      <ToggleButton style={{ textTransform: "None" }} value={0}>Now</ToggleButton>
    </ToggleButtonGroup>
  );
}
