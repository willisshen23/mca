export const skillData = [
  { name: '活动参与率分析', cat: '活动分析', desc: '统计参与人数及漏斗', tpl: '1. 参与率计算\n2. 分层分析' },
  { name: '客群行为标签分析', cat: '客群分析', desc: '识别高价值客群', tpl: '1. 标签提取\n2. 聚类分析' },
  { name: '渠道效果对比', cat: '渠道分析', desc: '多渠道 ROI 对比', tpl: '1. 渠道汇总\n2. ROI 计算' },
  { name: '活动ROI分析', cat: '财务分析', desc: '成本收益分析', tpl: '1. 成本统计\n2. 净 ROI' },
  { name: '转化路径分析', cat: '活动分析', desc: '全链路分析', tpl: '1. 路径梳理\n2. 流失节点' },
  { name: '风险客群识别', cat: '风控分析', desc: '异常行为检测', tpl: '1. 规则检测\n2. 风险评分' },
  { name: '产品偏好分析', cat: '客群分析', desc: '偏好建模', tpl: '1. 偏好提取\n2. 推荐策略' },
  { name: '时间序列趋势', cat: '通用分析', desc: '时序趋势识别', tpl: '1. 数据处理\n2. 趋势识别' }
];

export const onlineActivities = [
  { name: '2024年Q1理财节活动', type: '线上', start: '2024-01-15', end: '2024-01-31', goal: '新增 AUM 5000万', status: '已结束' },
  { name: '春节专属理财产品推广', type: '线上', start: '2024-02-05', end: '2024-02-25', goal: '产品认购转化率 > 5%', status: '已结束' },
  { name: 'APP信用卡分期专场', type: '线上', start: '2024-03-01', end: '2024-03-31', goal: '分期笔数增长 30%', status: '已结束' },
  { name: '私行客户线上沙龙', type: '线上', start: '2024-03-15', end: '2024-03-20', goal: '高净值客户参与 > 200人', status: '已结束' },
  { name: '数字人民币推广活动', type: '线上', start: '2024-04-01', end: '2024-04-30', goal: '数字钱包开通数 +1万', status: '进行中' }
];

export const reportBars = {
  customers: [
    { label: '25-35岁', value: 78 },
    { label: '36-45岁', value: 55 }
  ],
  channels: [
    { label: 'APP推送', value: 92 },
    { label: '微信H5', value: 74 }
  ]
};
