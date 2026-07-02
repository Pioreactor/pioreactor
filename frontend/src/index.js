import React from 'react';
import './index.css';
import App from './App';
import "./styles.css";
import "./prism.css";

import { createRoot } from 'react-dom/client';
const container = document.getElementById('root');
const root = createRoot(container); // createRoot(container!) if you use TypeScript


root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
