/* ==========================================================================
   FAB 统一风格 —— 顶部横向导航外壳（对应 BOHAI 的 src/components/Layout.tsx）
   --------------------------------------------------------------------------
   ⚠️ 排版与原文件完全一致：64px 顶栏（左 logo + 主导航，右 看板/设置/用户/退出）
      + max-w-1920 内容区 + 移动端下拉。只替换了 className 里的视觉取值：

        text-blue-600        → text-primary
        bg-gray-50           → bg-page（页面底改为纯白）
        border-blue-500 下划线 → 选中态改为 bg-primary-weak 圆角块
        shadow-sm / border-b → border-line + shadow-xs
        text-[10px] 任意字号     → text-2xs（11px，字阶内最小一档）
   原版在 md~lg 之间把导航文字截成前 4 个字，这个行为予以保留（只是把
   text-[10px] 换成字阶内的 text-2xs），不改变任何显示逻辑。
   ========================================================================== */
import { useState } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Users, TrendingUp, LogOut, Building2, Package, Briefcase,
  Settings, BarChart3, Menu, X,
} from 'lucide-react';
import { authService } from '../services/auth';
import { Button, Brand, NavLinkStyle } from '../ui';

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = authService.getCurrentUser();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navItems = [
    { path: '/',                 label: '工作台',       icon: TrendingUp },
    { path: '/workstation',      label: '智能工作台',   icon: Briefcase },
    { path: '/wechat-assistant', label: '企业微信助手', icon: Building2 },
    { path: '/customers',        label: '客户管理',     icon: Users },
    { path: '/products',         label: '产品管理',     icon: Package },
    { path: '/marketing',        label: '营销活动',     icon: Building2 },
  ];

  const isFullHeight =
    location.pathname === '/workstation' || location.pathname === '/wechat-assistant';

  return (
    <div className="min-h-screen bg-page">
      {/* ── 顶栏（h-16，与原版一致）──────────────────────────────── */}
      <nav className="sticky top-0 z-[100] bg-white border-b border-line shadow-xs">
        <div className="relative h-topbar max-w-content mx-auto px-gutter flex items-center gap-4">

          <button
            onClick={() => setMobileOpen(v => !v)}
            className="md:hidden w-ctl h-ctl rounded-md text-t2 hover:bg-primary-weaker hover:text-primary flex items-center justify-center"
            aria-label="菜单"
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>

          <Brand name="银行客户经理工作平台" />

          {/* 桌面端主导航 */}
          <div className="hidden md:flex items-center gap-1 min-w-0 overflow-x-auto fab-scroll">
            {navItems.map(item => {
              const Icon = item.icon;
              return (
                <Link key={item.path} to={item.path} title={item.label}
                      className={NavLinkStyle(location.pathname === item.path)}>
                  <Icon className="w-4 h-4 shrink-0" />
                  {/* 与原版一致：lg 以上显示全称，lg 以下截前 4 个字 */}
                  <span className="hidden lg:inline">{item.label}</span>
                  <span className="lg:hidden text-2xs">
                    {item.label.length > 4 ? item.label.substring(0, 4) : item.label}
                  </span>
                </Link>
              );
            })}
          </div>

          {/* 右侧操作区 */}
          <div className="ml-auto flex items-center gap-2 shrink-0">
            <Link to="/metrics" title="看板" className={NavLinkStyle(location.pathname === '/metrics')}>
              <BarChart3 className="w-4 h-4" /><span className="hidden sm:inline">看板</span>
            </Link>
            <Link to="/settings" title="设置" className={NavLinkStyle(location.pathname === '/settings')}>
              <Settings className="w-4 h-4" /><span className="hidden sm:inline">设置</span>
            </Link>
            <span className="hidden lg:inline text-sm text-t3 whitespace-nowrap">欢迎，{user?.name}</span>
            <Button size="sm" icon={<LogOut className="w-3.5 h-3.5" />} onClick={() => { authService.logout(); navigate('/login'); }}>
              退出
            </Button>
          </div>
        </div>

        {/* 移动端下拉 */}
        {mobileOpen && (
          <div className="md:hidden absolute left-0 right-0 bg-white border-b border-line shadow-md px-gutter py-2 z-[200]">
            {navItems.map(item => {
              const Icon = item.icon;
              const active = location.pathname === item.path;
              return (
                <Link key={item.path} to={item.path} onClick={() => setMobileOpen(false)}
                      className={`flex items-center gap-3 px-3 py-3 rounded-md text-sm font-medium ${
                        active ? 'bg-primary-weak text-primary' : 'text-t2 hover:bg-primary-weaker'}`}>
                  <Icon className="w-5 h-5 shrink-0" />{item.label}
                </Link>
              );
            })}
          </div>
        )}
      </nav>

      {/* ── 主内容区（与原版一致的两种模式）───────────────────────── */}
      <main className={isFullHeight
        ? 'h-[calc(100vh-64px)] overflow-hidden w-full max-w-content mx-auto px-gutter'
        : 'w-full max-w-content mx-auto px-gutter py-6 pb-12'}>
        <Outlet />
      </main>
    </div>
  );
}
