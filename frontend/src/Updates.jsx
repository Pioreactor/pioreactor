import React from "react";
import MarkdownView from 'react-showdown';
import LoadingButton from '@mui/lab/LoadingButton';

import Grid from '@mui/material/Grid';
import { styled } from '@mui/material/styles';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';
import {Typography} from '@mui/material';
import Snackbar from '@mui/material/Snackbar';
import Link from '@mui/material/Link';
import UpdateIcon from '@mui/icons-material/Update';
import Divider from '@mui/material/Divider';
import MenuItem from '@mui/material/MenuItem';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { useConfirm } from 'material-ui-confirm';
import UnderlineSpan from "./components/UnderlineSpan";
import SelectButton from "./components/SelectButton";
import FolderZipIcon from '@mui/icons-material/FolderZip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import Alert from '@mui/material/Alert';
import PioreactorsIcon from './components/PioreactorsIcon';
import Select from '@mui/material/Select';
import InputLabel from '@mui/material/InputLabel';
import FormControl from '@mui/material/FormControl';
import CloseIcon from '@mui/icons-material/Close';

const VisuallyHiddenInput = styled('input')({
  clip: 'rect(0 0 0 0)',
  clipPath: 'inset(50%)',
  height: 1,
  overflow: 'hidden',
  position: 'absolute',
  bottom: 0,
  left: 0,
  whiteSpace: 'nowrap',
  width: 1,
});

const lostRed = "#DE3618"


function UploadArchiveAndConfirm(props) {
  const [selectedFile, setSelectedFile] = React.useState(null);
  const [errorMsg, setErrorMsg] = React.useState(null);
  const [units, setUnits] = React.useState([]);
  const [selectedUnits, setSelectedUnits] = React.useState("$broadcast");
  const [isUploading, setIsUploading] = React.useState(false);
  const handleClose = props.onClose


  React.useEffect(() => {
    async function fetchUnits() {
      try {
        const response = await fetch(`/api/units`);
        if (response.ok) {
          const units = await response.json();
          setUnits(units.map(u => u.pioreactor_unit));
        } else {
          console.error('Failed to fetch units:', response.statusText);
        }
      } catch (error) {
        console.error('Error fetching units:', error);
      }
    };
    fetchUnits()
  }, [])



  const handleFileChange = (event) => {
    const file = event.target.files[0]

    if (/^release_\d{0,2}\.\d{0,2}\.\d{0,2}\w{0,6}\.zip$/.test(file.name)) {
      setSelectedFile(event.target.files[0]);
      setErrorMsg(null)
    }
    else {
      setErrorMsg("Not a valid release archive file. It should be a zip file, starting with `release_` and ending in `<version>.zip`. ")
    }
  };

  const handleFileUpload = async () => {
    setIsUploading(true)
    const formData = new FormData();
    formData.append('file', selectedFile);
    try {
      const response = await fetch('/api/system/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        // Handle non-2xx responses here
        const errorData = await response.json();
        throw new Error(errorData.error || 'Upload failed with status ' + response.status);
      }

      const data = await response.json();
      return data.save_path;
    } catch (error) {
      setErrorMsg(error.message)
      setIsUploading(false)
      return null;
    }
  };

  const handleUpdate = async (savePath) => {
    try {
      await fetch("/api/system/update_from_archive", {
        method: "POST",
        body: JSON.stringify({ release_archive_location: savePath, units: selectedUnits }),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
      });
    } catch (error) {
      setIsUploading(false)
      console.error(error);
    }
  };

  const handleUploadClick = async () => {
    const savePath = await handleFileUpload();

    if (savePath === null) {
      // Exit the function if there was a problem in handleFileUpload
      return;
    }

    await handleUpdate(savePath);
    handleClose();
    props.onSuccess()
  }


  const onSelectionChange = (event) => {
    setSelectedUnits(event.target.value);
  }

  return (
    <React.Fragment>
      <Dialog
        open={true}
        onClose={handleClose}
        aria-labelledby="alert-dialog-title"
        aria-describedby="alert-dialog-description"
      >
        <DialogTitle id="alert-dialog-title">
          {props.title}
          <IconButton
            aria-label="close"
            onClick={handleClose}
            sx={{
              position: 'absolute',
              right: 8,
              top: 8,
              color: (theme) => theme.palette.grey[500],
            }}
            size="large">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <DialogContentText id="alert-dialog-description">
            {props.description}
            <p>You can update the Pioreactor software from our pre-built zip files. First download the <code>release_*.zip</code> file from our <a href="https://github.com/Pioreactor/pioreactor/releases?q=prerelease%3Afalse&expanded=true" target="_blank" rel="noopener noreferrer" >Releases page</a>, and then upload the file.</p>
            <p>To avoid possible data interruptions, we suggest updating between running experiments.
            Learn more about <a href="https://docs.pioreactor.com/user-guide/updating-software#method-2-update-using-a-zip-file-and-the-ui" target="_blank" rel="noopener noreferrer">updating from a zip file</a>.</p>

            {units.length > 1 &&
            <Box sx={{my: 2}}>
              <FormControl sx={{mt: 2, minWidth: "195px"}} variant="outlined" size="small">
                <InputLabel >Units to update</InputLabel>
                <Select
                  labelId="configSelect"
                  value={selectedUnits ? selectedUnits : "$broadcast"}
                  onChange={onSelectionChange}
                  label="Units to update"
                >
                  {units.map((unit) => (
                    <MenuItem key={unit} value={unit}>{unit}</MenuItem>
                  ))}
                  <MenuItem value="$broadcast"><PioreactorsIcon fontSize="small" sx={{verticalAlign: "middle", margin: "0px 4px"}} />All Pioreactors</MenuItem>
                </Select>
              </FormControl>
            </Box>
          }


            <Box sx={{display: "flex", justifyContent: "start", mt: 3}}>
              <Button variant="text" component="label" sx={{textTransform: 'none'}}>Upload zip file <VisuallyHiddenInput onChange={handleFileChange} accept=".zip" type="file" /></Button>
              <Box sx={{m: 1, ml: 2, display: "flex", alignItems: "center", gap: 0.5}}>
                {selectedFile == null ? "" : (
                  <React.Fragment>
                    <span>{selectedFile.name}</span>
                    <CheckCircleIcon fontSize="small" sx={{ color: "success.main" }} />
                  </React.Fragment>
                )}
              </Box>
            </Box>
            <Box sx={{minHeight: "30px", alignItems: "center", display: "flex"}}>
              {errorMsg   ? <Alert severity="error">{errorMsg}</Alert>           : <React.Fragment/>}
            </Box>
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} color="secondary">Cancel</Button>
          <LoadingButton variant="contained" loading={isUploading} disabled={selectedFile == null} onClick={handleUploadClick}>Update</LoadingButton>
        </DialogActions>
      </Dialog>
    </React.Fragment>
  );
}


function UpdateSoftwareConfirmDialog(props) {
  const confirm = useConfirm();
  const [updating, setUpdating] = React.useState(false)
  const [openSnackbar, setOpenSnackbar] = React.useState(false)
  const [installOption, setInstallOption] = React.useState("archive")
  const [showArchiveConfirm, setShowArchiveConfirm] = React.useState(false);
  const [internetAccess, setInternetAccess] = React.useState(false);

  React.useEffect(() => {
    const checkConnectivity = () => {
      fetch(`https://www.google.com/favicon.ico?${new Date().getTime()}`, {method: 'GET', mode: 'no-cors'})
        .then(() => {
          setInternetAccess(true);
        })
        .catch(() => {
          setInternetAccess(false);
        })
    };
    // Check connectivity on mount
  checkConnectivity();
  }, []);

  const updateVersion = () => {
    setOpenSnackbar(true)
    if (installOption === "latest") {
      fetch("/api/system/update_next_version", {method: "POST"})
    }
  }

  const handleClick = () => {
    if (installOption === "archive") {
      // Open the UploadArchiveAndConfirm dialog
      setShowArchiveConfirm(true);
    }
    else {
      confirm({
        description: getDescription(),
        title: getTitle(),
        confirmationText: "Update",
        confirmationButtonProps: {color: "primary"},
        cancellationButtonProps: {color: "secondary"}, //style: {textTransform: 'none'}
        }).then(() => {
          updateVersion();
          setUpdating(true)
        }
      ).catch(() => {});

    }
  };

  const getIcon = () =>{
    if (installOption === "latest") {
      return <UpdateIcon/>
    }
    else if (installOption === "archive"){
      return <FolderZipIcon/>
    }
  }

  const getTitle = () => {
    if (installOption === "latest") {
      return "Update to next release?"
    }
    else if (installOption === "archive"){
      return "Update from zip file?"
    }
  }

  const getDescription = () => {
    if (installOption === "latest") {
      return "This requires an internet connection. To avoid possible data interruptions, we suggest updating between running experiments."
    }
    else if (installOption === "archive"){
      return ""

    }
  }

  return (
    <React.Fragment>
      <SelectButton
        buttonStyle={{textTransform: 'none'}}
        value={installOption}
        onClick={handleClick}
        onChange={({ target: { value } }) =>
          setInstallOption(value)
        }
        disabled={updating}
        endIcon={getIcon()}
      >
        <MenuItem disabled={!internetAccess} value={"latest"}>Update to next release over internet</MenuItem>
        <MenuItem value={"archive"}>Update from zip file</MenuItem>
      </SelectButton>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={openSnackbar}
        message="Updating in the background. This may take a few minutes. You may leave this page."
        autoHideDuration={20000}
        key="snackbar-update"
      />
      {showArchiveConfirm && (
        <UploadArchiveAndConfirm
          title={getTitle()}
          description={getDescription()}
          onSuccess={() => setOpenSnackbar(true)}
          onClose={() => setShowArchiveConfirm(false)}
        />
      )}
      </React.Fragment>
  );
}


function PageHeader(props) {
  const [version, setVersion] = React.useState("")
  const [uiVersion, setUIVersion] = React.useState("")
  const [latestVersion, setLatestVersion] = React.useState("")


  React.useEffect(() => {
    async function getCurrentAppVersion() {
         await fetch("/unit_api/versions/app")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setVersion(data['version'])
        });
      }

    async function getCurrentUIVersion() {
         await fetch("/unit_api/versions/ui")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setUIVersion(data['version'])
        });
      }

    async function getLatestAppVersion() {
         await fetch("https://api.github.com/repos/pioreactor/pioreactor/releases/latest")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setLatestVersion(data['tag_name'])
        })
        .catch(e => {
          console.log("No internet connection?")
        })
      }

      getCurrentUIVersion()
      getCurrentAppVersion()
      getLatestAppVersion()
  }, [])

  return (
    <Box>
      <Box sx={{display: "flex", justifyContent: "space-between", marginBottom: "5px"}}>
        <Typography variant="h5" component="h1">
          <Box fontWeight="fontWeightBold">
            Updates
          </Box>
        </Typography>
        <Box>
          <Box sx={{float: "right", marginRight: "0px", marginLeft: "10px"}}>
            <UpdateSoftwareConfirmDialog />
          </Box>
          <Link color="inherit" underline="none" href={`https://github.com/Pioreactor/pioreactor/releases/tag/${latestVersion}`} target="_blank" rel="noopener noreferrer">
            <Button sx={{textTransform: 'none', float: "right", marginRight: "0px"}} color="primary">
              <OpenInNewIcon fontSize="small" sx={{fontSize: 15, verticalAlign: "middle", margin: "0px 3px"}}/> View latest release
            </Button>
          </Link>
        </Box>
      </Box>
      <Divider/>
      <Typography variant="subtitle2">

        <Box fontWeight="fontWeightBold" style={{margin: "10px 2px 10px 2px", display:"inline-block"}}>
          <SystemUpdateAltIcon style={{ fontSize: 14, verticalAlign: "-1px" }}/> Version installed on leader:
        </Box>
        <Box fontWeight="fontWeightRegular" style={{marginRight: "20px", display:"inline-block"}}>
          {version}
        </Box>

        <Box fontWeight="fontWeightBold" style={{margin: "10px 2px 10px 2px", display:"inline-block"}}>
          <UpdateIcon style={{ fontSize: 14, verticalAlign: "-1px" }}/> Latest version available:
        </Box>
        <Box fontWeight="fontWeightRegular" style={{marginRight: "20px", display:"inline-block"}}>
          {latestVersion}
        </Box>

      </Typography>
    </Box>
  )
}



function ChangelogContainer(){

  const [changelog, setChangelog] = React.useState("")

  React.useEffect(() => {
    async function getData() {
         await fetch("https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md")
        .then((response) => {
          return response.text();
        })
        .then((data) => {
          setChangelog(data)
        }
        ).catch(e => {
          // no internet?
          setChangelog(`
Could not retrieve latest Changelog. Perhaps not connected to the internet.
 - You can find the latest changelog at this url: [https://github.com/pioreactor/pioreactor/master/CHANGELOG.md](https://github.com/pioreactor/pioreactor/master/CHANGELOG.md)
 - To update to the latest version of Pioreactor software, even without internet, see documentation here: [https://docs.pioreactor.com/user-guide/common-questions#im-using-a-local-access-point-but-id-like-to-install-plugins-update-software-etc](https://docs.pioreactor.com/user-guide/common-questions#im-using-a-local-access-point-but-id-like-to-install-plugins-update-software-etc).
          `)
        })
      }
      getData()
  }, [])


  return(
    <React.Fragment>
      <Card>
        <CardContent sx={{p: 1}}>
        <Typography variant="h6" component="h6">
            Change log
        </Typography>
          <MarkdownView
            markdown={changelog}
          />
        </CardContent>
      </Card>
    </React.Fragment>
)}


function Updates(props) {
    React.useEffect(() => {
    document.title = props.title;
  }, [props.title])
    return (
      <Grid container spacing={2} >
        <Grid
          size={{
            md: 12,
            xs: 12
          }}>
          <PageHeader/>
          <ChangelogContainer/>
        </Grid>
      </Grid>
    );
}

export default Updates;
