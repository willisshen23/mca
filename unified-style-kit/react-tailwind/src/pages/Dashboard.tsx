/* ==========================================================================
   FAB 统一风格 —— 工作台页（对应 BOHAI 的 src/pages/Dashboard.tsx）
   --------------------------------------------------------------------------
   ⚠️ 功能与原版逐项一致，未新增也未删减：
      页头 → 3 张可点击统计卡 → 客户等级分布 → 快速操作
   原版没有环比趋势行、没有筛选工具栏、没有客户表格（表格在 Customers.tsx）。

   视觉层改动：
     bg-blue-500/green-500/purple-500 纯色图标块 → 同色系浅底 + 主色图标
     shadow / shadow-md                          → shadow-xs / hover:shadow-md
     text-2xl / text-lg / text-sm                → text-h2 / text-h3 / text-sm
     text-gray-900 / -500                        → text-t1 / text-t3
   ========================================================================== */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Users, TrendingUp, Calendar, Activity } from 'lucide-react';
import { marketingService, type Stats } from '../services/marketing';

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const data = await marketingService.getStats();
      setStats(data);
    } catch (error) {
      console.error('加载统计数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-12 text-t3 text-sm">加载中...</div>;
  }

  // 与原版同样的三张卡；color 由纯色块改为浅底 + 同色图标
  const statCards = [
    { title: '客户总数',     value: stats?.totalCustomers  || 0, icon: Users,    tone: 'bg-primary-weak text-primary',      link: '/customers' },
    { title: '活跃营销活动', value: stats?.activeCampaigns || 0, icon: Activity, tone: 'bg-success-weak text-success',      link: '/marketing' },
    { title: '近30天跟进',   value: stats?.recentFollowUps || 0, icon: Calendar, tone: 'bg-violet-weak text-[#5A5FD6]',     link: '/customers' },
  ];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-h1 text-t1">工作台</h1>
        <p className="mt-2 text-sm text-t3">欢迎回来，查看您的工作概览</p>
      </div>

      {/* 统计卡片：整张卡可点击跳转，与原版一致 */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 mb-8">
        {statCards.map((card) => {
          const Icon = card.icon;
          return (
            <Link
              key={card.title}
              to={card.link}
              className="bg-white border border-line rounded-lg shadow-xs overflow-hidden
                         transition-all duration-200 hover:border-primary-border hover:shadow-md hover:-translate-y-0.5"
            >
              <div className="p-5 flex items-center gap-5">
                <div className={`${card.tone} p-3 rounded-md shrink-0`}>
                  <Icon className="h-6 w-6" />
                </div>
                <dl className="min-w-0">
                  <dt className="text-sm font-medium text-t3 truncate">{card.title}</dt>
                  <dd className="text-h2 text-t1 num">{card.value}</dd>
                </dl>
              </div>
            </Link>
          );
        })}
      </div>

      {/* 客户等级分布 */}
      {stats && stats.customersByLevel.length > 0 && (
        <div className="bg-white border border-line rounded-lg shadow-xs p-6 mb-8">
          <h2 className="text-h3 text-t1 mb-4">客户等级分布</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {stats.customersByLevel.map((item) => (
              <div key={item.customer_level} className="text-center">
                <div className="text-h1 text-primary num">{item.count}</div>
                <div className="text-sm text-t3 mt-1">{item.customer_level || '未分类'}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 快速操作 */}
      <div className="bg-white border border-line rounded-lg shadow-xs p-6">
        <h2 className="text-h3 text-t1 mb-4">快速操作</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Link
            to="/customers"
            className="flex items-center p-4 border border-line rounded-md transition-colors
                       hover:border-primary-border hover:bg-primary-weaker"
          >
            <Users className="h-5 w-5 text-primary mr-3 shrink-0" />
            <div>
              <div className="font-medium text-t1">添加新客户</div>
              <div className="text-sm text-t3">录入客户信息</div>
            </div>
          </Link>
          <Link
            to="/marketing"
            className="flex items-center p-4 border border-line rounded-md transition-colors
                       hover:border-primary-border hover:bg-primary-weaker"
          >
            <TrendingUp className="h-5 w-5 text-success mr-3 shrink-0" />
            <div>
              <div className="font-medium text-t1">创建营销活动</div>
              <div className="text-sm text-t3">发起新的营销活动</div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}
