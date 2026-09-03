### Development

#### `npm run start`

Runs the app in the development mode.<br />
Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

The page will reload if you make edits.<br />
Run `npm run lint` or `make frontend-lint` from the repository root to check lint errors.

Run `npm test -- --runInBand` for frontend tests. Tests require Node 24.9+;
the test command enables Jest's VM modules support to load React Router v8's ESM package.


### Production


```
npm run build
```

Builds the app for production to the `build` folder.<br />
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.<br />
