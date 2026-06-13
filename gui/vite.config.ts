import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  server: {
    port: 1420,
    strictPort: true,
    watch: {
      // Impede o Vite de monitorar a pasta de build do Rust
      ignored: ["**/src-tauri/**"],
    },
  },

  clearScreen: false,
});