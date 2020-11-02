import React from "react";

import Grid from '@material-ui/core/Grid';
import Header from "./components/Header"

import CssBaseline from "@material-ui/core/CssBaseline";
import { MuiThemeProvider, createMuiTheme } from "@material-ui/core/styles";

const themeLight = createMuiTheme({
  palette: {
    background: {
      default: "#fafbfc"
    }
  }
});


function DownloadDataForm(){
  return (
    <div> Test </div>
  )

}


function DownloadData() {
    return (
    <MuiThemeProvider theme={themeLight}>
      <CssBaseline />
      <div>
        <Grid container spacing={2} >
          <Grid item xs={12}><Header /></Grid>

          <Grid item xs={2}/>
          <Grid item xs={8}>
            <div> <DownloadDataForm/> </div>
          </Grid>
          <Grid item xs={2}/>
        </Grid>
      </div>
    </MuiThemeProvider>
    )
}
export default DownloadData;
