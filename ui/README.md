### Development

All from the `/ui` folder.

#### `npm start`

Runs the app in the development mode.<br />
Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

The page will reload if you make edits.<br />
You will also see any lint errors in the console.


### Production

#### `npm run build`

Builds the app for production to the `build` folder.<br />
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.<br />
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

### Deployment

The entry point is `app.js`, which has a basic auth in front of it.

### `BASIC_AUTH_ADMIN=admin BASIC_AUTH_PASS=<pass> pm2 start app.js --name ui`

Open [http://localhost:9000](http://localhost:9000) to view it in the browser.
