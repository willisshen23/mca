"""Pydantic schemas for marketing campaign data."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Campaign(BaseModel):
    """活动数据模型."""

    model_config = ConfigDict(populate_by_name=True)

    data_date: Optional[date] = Field(default=None, alias="数据日期")
    activity_id: Optional[str] = Field(default=None, alias="活动编号")
    activity_name: Optional[str] = Field(default=None, alias="活动名称")
    start_date: Optional[date] = Field(default=None, alias="活动开始日期")
    end_date: Optional[date] = Field(default=None, alias="活动结束日期")
    content: Optional[str] = Field(default=None, alias="活动内容")
    participant_count: Optional[int] = Field(default=None, alias="活动运营人数")
    status: Optional[str] = Field(default=None, alias="活动状态")
    target: Optional[str] = Field(default=None, alias="活动运营目标")
    activity_type: Optional[str] = Field(default=None, alias="活动类型")
    channel: Optional[str] = Field(default=None, alias="活动渠道")
    target_segment: Optional[str] = Field(default=None, alias="目标客群")
    current_aum: Optional[float] = Field(default=None, alias="当前AUM时点值")
    last_month_aum: Optional[float] = Field(default=None, alias="上月末AUM时点值")
    avg_aum: Optional[float] = Field(default=None, alias="人均aum值")
    avg_aum_increase: Optional[float] = Field(default=None, alias="人均aum提升额")
    valuable_customers: Optional[int] = Field(default=None, alias="价值客户数")
    valuable_customer_ratio: Optional[float] = Field(default=None, alias="价值客户占比")
    valuable_customer_increase: Optional[int] = Field(default=None, alias="价值客户提升数")
    converted_valuable_customers: Optional[int] = Field(default=None, alias="转化价值客户数")
    lost_valuable_customers: Optional[int] = Field(default=None, alias="流失价值客户数")
    deposit_balance: Optional[float] = Field(default=None, alias="存款余额")
    deposit_non_current: Optional[float] = Field(default=None, alias="存款余额（非活期）")
    avg_deposit_balance: Optional[float] = Field(default=None, alias="人均存款余额")
    avg_deposit_increase: Optional[float] = Field(default=None, alias="存款人均提升额")
    wealth_balance: Optional[float] = Field(default=None, alias="理财余额")
    last_month_wealth: Optional[float] = Field(default=None, alias="上个月理财余额")
    avg_wealth_balance: Optional[float] = Field(default=None, alias="人均理财余额")
    avg_wealth_increase: Optional[float] = Field(default=None, alias="理财人均提升额")
    fund_balance: Optional[float] = Field(default=None, alias="基金余额")
    avg_fund_increase: Optional[float] = Field(default=None, alias="人均基金余额提升额")
    aum_above_1k_customers: Optional[int] = Field(default=None, alias="AUM千元以上客户数")
    converted_aum_above_1k: Optional[int] = Field(default=None, alias="转化AUM千元客户数")
    lum_qualified_customers: Optional[int] = Field(default=None, alias="LUM达标客户数")
    converted_lum_qualified: Optional[int] = Field(default=None, alias="转化LUM达标客户数")
    cc_valuable_customers: Optional[int] = Field(default=None, alias="信用卡价值达标客户数")
    converted_cc_valuable: Optional[int] = Field(default=None, alias="转化信用卡价值达标客户数")
    gold_card_above_customers: Optional[int] = Field(default=None, alias="金卡（含）以上客户数")
    converted_gold_card: Optional[int] = Field(default=None, alias="转化金卡（含）以上客户数")
    new_payroll_customers: Optional[int] = Field(default=None, alias="新增有效代发客户数")
    lost_aum_above_1k: Optional[int] = Field(default=None, alias="流失AUM千元以上客户数")
    lost_gold_card: Optional[int] = Field(default=None, alias="流失金卡（含）以上客户数")
    lost_lum_qualified: Optional[int] = Field(default=None, alias="流失LUM达标客户数")
    lost_payroll_customers: Optional[int] = Field(default=None, alias="流失有效代发客户数")
    avg_product_coverage: Optional[float] = Field(default=None, alias="人均产品覆盖数")
    avg_product_coverage_increase: Optional[float] = Field(default=None, alias="人均产品覆盖提升数")
    payroll_retention_rate: Optional[float] = Field(default=None, alias="近一年代发资金留存率")
    payroll_retention_increase: Optional[float] = Field(default=None, alias="近一年代发资金留存提升率")
    avg_signed_services: Optional[int] = Field(default=None, alias="人均开通签约类服务的数量")
    avg_signed_services_increase: Optional[float] = Field(default=None, alias="人均开通签约类服务的提升数")
    avg_transactions_per_year: Optional[int] = Field(default=None, alias="近一年人均动账次数")
    avg_transaction_amount: Optional[int] = Field(default=None, alias="人均动账金额")
    avg_transaction_increase: Optional[float] = Field(default=None, alias="人均动账次数提升")
    avg_transaction_amount_increase: Optional[float] = Field(default=None, alias="人均动账金额提升")
    mau: Optional[int] = Field(default=None, alias="月活跃客户数（mau)")
    mau_increase: Optional[int] = Field(default=None, alias="月活跃客户数提升数")
    valuable_customer_growth_rate: Optional[float] = Field(default=None, alias="价值客户提升率")
    financial_asset_increase: Optional[float] = Field(default=None, alias="金融资产提升额")
    deposit_increase: Optional[float] = Field(default=None, alias="存款提升额")
    wealth_increase: Optional[float] = Field(default=None, alias="理财提升额")
    app_transaction_active_rate: Optional[float] = Field(default=None, alias="APP动账活跃提升率")
    maturing_product_count: Optional[int] = Field(default=None, alias="到期理财产品数")
    maturing_product_amount: Optional[float] = Field(default=None, alias="到期理财金额")
    maturing_customer_count: Optional[int] = Field(default=None, alias="到期客户数")
    maturity_conversion_rate: Optional[float] = Field(default=None, alias="到期后转化率")
    maturity_repurchase_amount: Optional[float] = Field(default=None, alias="到期后再购金额")
    maturity_repurchase_customers: Optional[int] = Field(default=None, alias="到期后再购客户数")

    def model_dump_by_alias(self, **kwargs):
        """序列化时使用中文别名作为键名."""
        return self.model_dump(by_alias=True, **kwargs)


class CampaignSearchResponse(BaseModel):
    """活动查询响应模型."""

    total: int = Field(description="匹配总数")
    campaigns: list[Campaign] = Field(description="活动列表")
