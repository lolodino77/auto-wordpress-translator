import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// « npm run build » écrit l'interface dans webapp/static, servie par « python -m webapp ».
// « npm run dev » (développement) renvoie les appels /api vers le serveur Python lancé à côté.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "../webapp/static", emptyOutDir: true, chunkSizeWarningLimit: 800 },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8710", changeOrigin: true } },
  },
});
