import { defineConfig, transformWithEsbuild } from "vite";
import react from "@vitejs/plugin-react";

function transformJsFilesWithJsx() {
  return {
    name: "transform-js-files-with-jsx",
    enforce: "pre",
    async transform(code, id) {
      const filePath = id.split("?")[0];
      if (!/src\/.*\.js$/.test(filePath)) {
        return null;
      }

      return transformWithEsbuild(code, filePath, {
        loader: "jsx",
        jsx: "automatic",
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

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/static/" : "/",
  plugins: [
    serveStaticPublicAssetsFromProductionPath(),
    transformJsFilesWithJsx(),
    react({ include: /\.(js|jsx|ts|tsx)$/ }),
  ],
  optimizeDeps: {
    entries: ["index.html"],
    esbuildOptions: {
      loader: {
        ".js": "jsx",
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:4999",
      "/unit_api": "http://localhost:4999",
      "/mcp": "http://localhost:4999",
      "/exports": "http://localhost:4999",
    },
  },
  build: {
    assetsDir: "static",
    outDir: "build",
    rollupOptions: {
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
