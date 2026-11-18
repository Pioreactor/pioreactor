import { defineConfig, transformWithOxc } from "vite";
import react from "@vitejs/plugin-react";

// Prism's language modules read a free Prism variable. Give them an explicit
// dependency so the core initializes before the language modules run.
const prismTransform = { inject: { Prism: ["prismjs", "default"] } };

function transformJsFilesWithJsx() {
  return {
    name: "transform-js-files-with-jsx",
    enforce: "pre",
    async transform(code, id) {
      const filePath = id.split("?")[0];
      if (!/src\/.*\.js$/.test(filePath)) {
        return null;
      }

      return transformWithOxc(code, filePath, {
        lang: "jsx",
        jsx: { runtime: "automatic", development: false },
      });
    },
  };
}

function serveStaticPublicAssetsFromProductionPath() {
  return {
    name: "serve-static-public-assets-from-production-path",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url?.startsWith("/static/")) {
          req.url = req.url.slice("/static".length);
        }
        next();
      });
    },
  };
}

// The touchscreen UI lives under /k/ (see KIOSK.md). In development, serve its own
// HTML entry for those paths, so the kiosk never loads the main app's bundle.
function serveKioskEntryUnderK() {
  return {
    name: "serve-kiosk-entry-under-k",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = req.url?.split("?")[0];
        if (path === "/k" || path?.startsWith("/k/")) {
          req.url = "/kiosk.html";
        }
        next();
      });
    },
  };
}

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/static/" : "/",
  plugins: [
    serveStaticPublicAssetsFromProductionPath(),
    serveKioskEntryUnderK(),
    transformJsFilesWithJsx(),
    react({ include: /\.(js|jsx|ts|tsx)$/ }),
  ],
  optimizeDeps: {
    entries: ["index.html", "kiosk.html"],
    rolldownOptions: {
      transform: prismTransform,
      moduleTypes: {
        ".js": "jsx",
      },
    },
  },
  server: {
    proxy: {
      "/mqtt": { target: "ws://127.0.0.1:9001", ws: true },
      "/api": "http://localhost:4999",
      "/unit_api": "http://localhost:4999",
      "/mcp": "http://localhost:4999",
      "/exports": "http://localhost:4999",
    },
  },
  build: {
    assetsDir: "static",
    outDir: "build",
    // Keep the browser baseline from Vite 7 for both entry points.
    target: ["chrome107", "edge107", "firefox104", "safari16"],
    rolldownOptions: {
      transform: prismTransform,
      // kiosk.html is the lean touchscreen UI each Pioreactor serves under /k/.
      input: {
        main: "index.html",
        kiosk: "kiosk.html",
      },
      output: {
        // Shared modules otherwise become dozens of sub-kilobyte chunks (single icons, small MUI
        // components), each its own HTTP/1.1 request on a route's first load.
        codeSplitting: {
          includeDependenciesRecursively: false,
          groups: [{ name: "mui", test: /\/node_modules\/@mui\// }],
        },
      },
      onwarn(warning, defaultHandler) {
        const source = warning.id?.replaceAll("\\", "/");
        const isKnownLegacyChartEval =
          warning.code === "EVAL" &&
          (source?.endsWith("/src/ExperimentOverview.jsx") ||
            source?.endsWith("/src/Pioreactor.jsx"));

        if (!isKnownLegacyChartEval) {
          defaultHandler(warning);
        }
      },
    },
  },
}));
