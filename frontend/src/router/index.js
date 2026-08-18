import { createRouter, createWebHistory } from 'vue-router';
import HomeView from '../views/HomeView.vue';
import SourceConfigView from '../views/SourceConfigView.vue';
import SkillComposerView from '../views/SkillComposerView.vue';
import ReportView from '../views/ReportView.vue';
import SkillManagementView from '../views/SkillManagementView.vue';
import HistoryView from '../views/HistoryView.vue';
import ConversationLogsView from '../views/ConversationLogsView.vue';
import TemplateView from '../views/TemplateView.vue';
import UiChatView from '../views/UiChatView.vue';
import SettingsView from '../views/SettingsView.vue';
import LogsView from '../views/LogsView.vue';

const routes = [
  { path: '/', redirect: '/chat-ui' },
  { path: '/management', name: 'management', component: HomeView },
  { path: '/analysis/:type(online|offline)/source', name: 'source', component: SourceConfigView },
  { path: '/analysis/compose', name: 'compose', component: SkillComposerView },
  { path: '/analysis/report', name: 'report', component: ReportView },
  { path: '/skills', name: 'skills', component: SkillManagementView },
  { path: '/history', name: 'history', component: HistoryView },
  { path: '/conversation-logs', name: 'conversation-logs', component: ConversationLogsView },
  { path: '/templates', name: 'templates', component: TemplateView },
  { path: '/logs', name: 'logs', component: LogsView },
  { path: '/settings', name: 'settings', component: SettingsView },
  { path: '/chat-ui', name: 'chat-ui', component: UiChatView, meta: { standalone: true } },
  { path: '/:pathMatch(.*)*', redirect: '/chat-ui' }
];

export default createRouter({
  history: createWebHistory(),
  routes
});
