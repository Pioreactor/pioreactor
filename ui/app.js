const express = require('express');
const basicAuth = require('express-basic-auth')
const path = require('path');
const app = express();

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

app.listen(9000);
