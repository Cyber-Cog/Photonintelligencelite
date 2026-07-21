import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";
var plotlyMin = path.resolve(__dirname, "node_modules/plotly.js-dist-min/plotly.min.js");
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: [
            { find: "@", replacement: path.resolve(__dirname, "src") },
            // react-plotly.js requires "plotly.js/dist/plotly"; map both that path and the
            // package root to the lean dist-min bundle.
            { find: "plotly.js/dist/plotly", replacement: plotlyMin },
            { find: /^plotly\.js$/, replacement: plotlyMin },
        ],
    },
    server: {
        port: 5173,
        host: true,
        proxy: {
            // Same-origin /api so template downloads and large fetches avoid cross-origin friction.
            "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
        },
    },
});
