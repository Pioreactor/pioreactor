const express = require('express');
const basicAuth = require('express-basic-auth')
const path = require('path');
const app = express();
const { exec } = require("child_process");


// load persistent data
const chartData135 = require('./data/implied_135.json')[0];
const chartGrowthRate = require('./data/implied_growth_rate.json')[0];
const chartAltMediaFraction = require('./data/alt_media_fraction.json')[0];
const listOfLogs = require('./data/all_morbidostat.log.json');


// this is not secure, and I know it. It's fine for now, as the app isn't exposed to the internet.
var staticUserAuth = basicAuth({
    users: {
        [process.env['BASIC_AUTH_ADMIN']]: process.env['BASIC_AUTH_PASS']
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

app.listen(9000);
