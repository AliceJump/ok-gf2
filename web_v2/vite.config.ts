import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// 构建产物放在 web_v2/static（仓库 .gitignore 忽略了 dist/ 和 build/，static 会随仓库提交，
// Windows 侧不用装 node）。serve_web_v2.py 把 static 挂在 /v2。
const proxy = {
  "/api/events": { target: "ws://127.0.0.1:8765", ws: true },
  "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
};

export default defineConfig({
  base: "/v2/",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: { outDir: "static", emptyOutDir: true },
  // 本机联调：/api 代理到 ok-script 后端（真后端或 mock/server.mjs）
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
});
