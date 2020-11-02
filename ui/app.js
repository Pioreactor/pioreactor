const express = require('express');
const basicAuth = require('express-basic-auth')
const path = require('path');
const app = express();
const { exec } = require("child_process");
const url = require('url');


var sqlite3 = require('sqlite3').verbose()
var db = new sqlite3.Database('~/db/morbidostat.sql:')

// this is not secure, and I know it. It's fine for now, as the app isn't exposed to the internet.
var staticUserAuth = basicAuth({
    users: {
        //[process.env['BASIC_AUTH_ADMIN']]: process.env['BASIC_AUTH_PASS']
        admin: "admin"
    },
    challenge: true
})


app.get('/', staticUserAuth, function(req, res) {
    app.use(express.static(path.join(__dirname, 'build')));
    res.sendFile(path.join(__dirname, 'build', 'index.html'));
})

app.get('/stop', function (req, res) {
    exec("mba kill python -y", (error, stdout, stderr) => {
        if (error) {
            res.send(`error: ${error.message}`);
            return;
        }
        if (stderr) {
            res.send(`stderr: ${stderr}`);
            return;
        }
        console.log(`stdout: ${stdout}`);
    });
})

app.get('/add_media/:unit', function (req, res) {

    const queryObject = url.parse(req.url, true).query;
    options = ("mL" in queryObject) ? ["--mL", queryObject['mL']] : ["--duration", queryObject['duration']]
    command = (["mba", "add_media", "-y", "--units", req.params.unit].concat(options)).join(" ")

    exec(command, (error, stdout, stderr) => {
        if (error) {
            res.send(`error: ${error.message}`);
            return;
        }
        if (stderr) {
            res.send(`stderr: ${stderr}`);
            return;
        }
        console.log(`stdout: ${stdout}`);
    });
})

app.get('/add_alt_media/:unit', function (req, res) {
    const queryObject = url.parse(req.url, true).query;
    options = ("mL" in queryObject) ? ["--mL", queryObject['mL']] : ["--duration", queryObject['duration']]
    command = (["mba", "add_alt_media", "-y", "--units", req.params.unit].concat(options)).join(" ")
    exec(command, (error, stdout, stderr) => {
        if (error) {
            res.send(`error: ${error.message}`);
            return;
        }
        if (stderr) {
            res.send(`stderr: ${stderr}`);
            return;
        }
        console.log(`stdout: ${stdout}`);
    });
})


app.get('/remove_waste/:unit', function (req, res) {
    const queryObject = url.parse(req.url, true).query;
    options = ("mL" in queryObject) ? ["--mL", queryObject['mL']] : ["--duration", queryObject['duration']]
    command = (["mba", "remove_waste", "-y", "--units", req.params.unit].concat(options)).join(" ")
    exec(command, (error, stdout, stderr) => {
        if (error) {
            res.send(`error: ${error.message}`);
            return;
        }
        if (stderr) {
            res.send(`stderr: ${stderr}`);
            return;
        }
        console.log(`stdout: ${stdout}`);
    });
})


app.get('/start_experiment/', staticUserAuth, function (req, res) {
  app.use(express.static(path.join(__dirname, 'build')));
  res.sendFile(path.join(__dirname, 'build', 'start_experiment.html'));
})

app.get('/download_data/', staticUserAuth, function (req, res) {
  app.use(express.static(path.join(__dirname, 'build')));
  res.sendFile(path.join(__dirname, 'build', 'download_data.html'));
})

app.get('/edit_config/', staticUserAuth, function (req, res) {
  app.use(express.static(path.join(__dirname, 'build')));
  res.sendFile(path.join(__dirname, 'build', 'index.html'));
})


app.get('/get_experiments/', function (req, res) {
  db.each('SELECT rowid AS id, info FROM lorem', function (err, row) {
   console.log(row.id + ': ' + row.info)
  })
  res.sendFile(path.join(__dirname, 'build', 'index.html'));
})



app.listen(9000);
