import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import './assets/styles.css';

// Hash 路由兼容入口：旧 history 模式链接（如 /main/analysis/report?srcSysNo=x）
// 重写到 /?srcSysNo=x#/main/analysis/report，search 前置保留供页面挂参读取，
// 避免外部系统入口或书签在 hash 模式下落到默认页
if (
  window.location.pathname !== '/' &&
  window.location.pathname !== '/index.html' &&
  !window.location.hash.startsWith('#/')
) {
  window.location.replace(`/${window.location.search}#${window.location.pathname}`);
}

createApp(App).use(router).mount('#app');
