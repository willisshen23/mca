import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const devApiTarget = env.VITE_DEV_API_TARGET || 'http://localhost:9111';

  return {
    // 静态资源一律使用相对路径（./assets/*、./lib/* 等），
    // 保证部署在网关子路径（如 /data-ai/）下也能正确加载
    base: './',
    plugins: [vue()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/activity/api': {
          target: devApiTarget,
          changeOrigin: true,
        },
        // AuthSDK 鉴权接口（后端再反向代理到鉴权服务）
        '/activity/authApi': {
          target: devApiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
