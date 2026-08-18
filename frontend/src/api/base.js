// 后端 API 基地址。
// - 本地开发：留空时默认使用 '/api'，由 vite.config.js 的 proxy 转发到 http://127.0.0.1:8000
// - 生产环境：在 .env.production 中通过 VITE_API_BASE_URL 配置完整地址，例如
//     VITE_API_BASE_URL=https://your-domain.com/api
//   或          VITE_API_BASE_URL=http://192.168.1.100:8000/api
// 注意：不要以 '/' 结尾，因为各请求路径已自带前导斜杠（如 '/env-config'）。
const rawBase = (import.meta.env.VITE_API_BASE_URL || '/api').trim();

export const API_BASE = rawBase.replace(/\/+$/, '');
