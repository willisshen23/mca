"""Pydantic schemas for 外呼活动 (outbound campaign) mock API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WaihuBasicInfo(BaseModel):
    """活动基本信息."""

    model_config = ConfigDict(extra="allow")

    act_no: Optional[str] = Field(default=None, description="活动编号")
    push_cust_subj: Optional[str] = Field(default=None, description="推送客户主体")
    act_proc_no: Optional[str] = Field(default=None, description="活动流程编号")
    push_task_name: Optional[str] = Field(default=None, description="推送任务名称")
    push_task_remark: Optional[str] = Field(default=None, description="推送任务备注")
    act_name: Optional[str] = Field(default=None, description="活动名称")
    活动审核通过时间: Optional[str] = Field(default=None, description="活动审核通过时间")
    活动开始时间: Optional[str] = Field(default=None, description="活动开始时间")
    活动结束时间: Optional[str] = Field(default=None, description="活动结束时间")
    活动状态: Optional[str] = Field(default=None, description="活动状态")
    活动目标: Optional[str] = Field(default=None, description="活动目标")
    创建人编号: Optional[str] = Field(default=None, description="创建人编号")
    创建人名称: Optional[str] = Field(default=None, description="创建人名称")
    创建机构名称: Optional[str] = Field(default=None, description="创建机构名称")
    活动人数: Optional[int] = Field(default=None, description="活动人数")
    yewu_type: Optional[str] = Field(default=None, description="业务类型")


class WaihuExecution(BaseModel):
    """外呼执行情况."""

    model_config = ConfigDict(extra="allow")

    act_no: Optional[str] = Field(default=None, description="活动编号")
    act_name: Optional[str] = Field(default=None, description="活动名称")
    yewu_type: Optional[str] = Field(default=None, description="业务类型")
    外呼执行天数: Optional[int] = Field(default=None, description="外呼执行天数")
    外呼人数: Optional[int] = Field(default=None, description="外呼人数")
    外呼成功人数: Optional[int] = Field(default=None, description="外呼成功人数")
    上午外呼成功人数: Optional[int] = Field(default=None, description="上午外呼成功人数")
    下午外呼成功人数: Optional[int] = Field(default=None, description="下午外呼成功人数")
    外呼失败人数: Optional[int] = Field(default=None, description="外呼失败人数")
    上午外呼失败人数: Optional[int] = Field(default=None, description="上午外呼失败人数")
    下午外呼失败人数: Optional[int] = Field(default=None, description="下午外呼失败人数")
    外呼成功平均通话时间: Optional[float] = Field(default=None, description="外呼成功平均通话时间")
    有效通话人数: Optional[int] = Field(default=None, description="有效通话人数")
    上午有效通话人数: Optional[int] = Field(default=None, description="上午有效通话人数")
    下午有效通话人数: Optional[int] = Field(default=None, description="下午有效通话人数")
    无效通话人数: Optional[int] = Field(default=None, description="无效通话人数")
    感兴趣人数: Optional[int] = Field(default=None, description="感兴趣人数")
    待定人数: Optional[int] = Field(default=None, description="待定人数")
    不感兴趣人数: Optional[int] = Field(default=None, description="不感兴趣人数")
    黑名单人数: Optional[int] = Field(default=None, description="黑名单人数")


class WaihuProductTransaction(BaseModel):
    """客户产品交易情况（外呼所有/联系失败/联系成功/有效通话客户）."""

    model_config = ConfigDict(extra="allow")

    客群范围: Optional[str] = Field(default=None, description="客群范围")
    act_no: Optional[str] = Field(default=None, description="活动编号")
    act_name: Optional[str] = Field(default=None, description="活动名称")
    外呼人数: Optional[int] = Field(default=None, description="外呼人数")
    外呼7日内点击理财人数: Optional[int] = Field(default=None, description="外呼7日内点击理财人数")
    外呼7日内购买理财人数: Optional[int] = Field(default=None, description="外呼7日内购买理财人数")
    外呼7日内购买理财金额: Optional[float] = Field(default=None, description="外呼7日内购买理财金额")
    外呼7日内购买理财金额大于100万人数: Optional[int] = Field(
        default=None, description="外呼7日内购买理财金额大于100万人数"
    )
    外呼7日内购买理财金额大于100万金额: Optional[float] = Field(
        default=None, description="外呼7日内购买理财金额大于100万金额"
    )
    外呼7日内点击存款人数: Optional[int] = Field(default=None, description="外呼7日内点击存款人数")
    外呼7日内购买存款人数: Optional[int] = Field(default=None, description="外呼7日内购买存款人数")
    外呼7日内购买存款金额: Optional[float] = Field(default=None, description="外呼7日内购买存款金额")
    外呼7日内购买存款金额大于100万人数: Optional[int] = Field(
        default=None, description="外呼7日内购买存款金额大于100万人数"
    )
    外呼7日内购买存款金额大于100万金额: Optional[float] = Field(
        default=None, description="外呼7日内购买存款金额大于100万金额"
    )


class WaihuProductTop5(BaseModel):
    """有效通话客户产品交易 TOP5/10."""

    model_config = ConfigDict(extra="allow")

    act_no: Optional[str] = Field(default=None, description="活动编号")
    act_name: Optional[str] = Field(default=None, description="活动名称")
    购买产品top10: Optional[str] = Field(default=None, description="购买产品top10原始文本")


class WaihuFundSource(BaseModel):
    """有效通话客户存款/理财购买资金来源."""

    model_config = ConfigDict(extra="allow")

    act_no: Optional[str] = Field(default=None, description="活动编号")
    act_name: Optional[str] = Field(default=None, description="活动名称")
    客群范围: Optional[str] = Field(default=None, description="客群范围")
    购买存款人数: Optional[int] = Field(default=None, description="购买存款人数")
    购买理财人数: Optional[int] = Field(default=None, description="购买理财人数")
    新资金引入人数: Optional[int] = Field(default=None, description="新资金引入人数")
    资金流失人数: Optional[int] = Field(default=None, description="资金流失人数")
    活期转存人数: Optional[int] = Field(default=None, description="活期转存人数")
    产品搬家人数: Optional[int] = Field(default=None, description="产品搬家人数")


class WaihuFundConversion(BaseModel):
    """客户资金转化情况."""

    model_config = ConfigDict(extra="allow")

    客群范围: Optional[str] = Field(default=None, description="客群范围")
    act_no: Optional[str] = Field(default=None, description="活动编号")
    act_name: Optional[str] = Field(default=None, description="活动名称")
    外呼人数: Optional[int] = Field(default=None, description="外呼人数")
    外呼3日后金融资产提升人数: Optional[int] = Field(default=None, description="外呼3日后金融资产提升人数")
    外呼7日后金融资产提升人数: Optional[int] = Field(default=None, description="外呼7日后金融资产提升人数")
    外呼3日后活期余额提升人数: Optional[int] = Field(default=None, description="外呼3日后活期余额提升人数")
    外呼7日后活期余额提升人数: Optional[int] = Field(default=None, description="外呼7日后活期余额提升人数")
    外呼3日后定存余额提升人数: Optional[int] = Field(default=None, description="外呼3日后定存余额提升人数")
    外呼7日后定存余额提升人数: Optional[int] = Field(default=None, description="外呼7日后定存余额提升人数")
    外呼3日后理财余额提升人数: Optional[int] = Field(default=None, description="外呼3日后理财余额提升人数")
    外呼7日后理财余额提升人数: Optional[int] = Field(default=None, description="外呼7日后理财余额提升人数")
    外呼3日后金融资产提升: Optional[float] = Field(default=None, description="外呼3日后金融资产提升")
    外呼7日后金融资产提升: Optional[float] = Field(default=None, description="外呼7日后金融资产提升")
    外呼3日后活期余额提升: Optional[float] = Field(default=None, description="外呼3日后活期余额提升")
    外呼7日后活期余额提升: Optional[float] = Field(default=None, description="外呼7日后活期余额提升")
    外呼3日后定存余额提升: Optional[float] = Field(default=None, description="外呼3日后定存余额提升")
    外呼7日后定存余额提升: Optional[float] = Field(default=None, description="外呼7日后定存余额提升")
    外呼3日后理财余额提升: Optional[float] = Field(default=None, description="外呼3日后理财余额提升")
    外呼7日后理财余额提升: Optional[float] = Field(default=None, description="外呼7日后理财余额提升")
    外呼3日后人均金融资产提升: Optional[float] = Field(default=None, description="外呼3日后人均金融资产提升")
    外呼7日后人均金融资产提升: Optional[float] = Field(default=None, description="外呼7日后人均金融资产提升")
    外呼3日后人均活期余额提升: Optional[float] = Field(default=None, description="外呼3日后人均活期余额提升")
    外呼7日后人均活期余额提升: Optional[float] = Field(default=None, description="外呼7日后人均活期余额提升")
    外呼3日后人均定存余额提升: Optional[float] = Field(default=None, description="外呼3日后人均定存余额提升")
    外呼7日后人均定存余额提升: Optional[float] = Field(default=None, description="外呼7日后人均定存余额提升")
    外呼3日后人均理财余额提升: Optional[float] = Field(default=None, description="外呼3日后人均理财余额提升")
    外呼7日后人均理财余额提升: Optional[float] = Field(default=None, description="外呼7日后人均理财余额提升")


class WaihuActivityDetail(BaseModel):
    """外呼活动完整详情."""

    act_no: str = Field(description="活动编号")
    basic_info: WaihuBasicInfo = Field(description="活动基本信息")
    execution: WaihuExecution = Field(description="外呼执行情况")
    all_customers_prodtxn: WaihuProductTransaction = Field(description="外呼所有客户产品交易情况")
    failed_customers_prodtxn: WaihuProductTransaction = Field(description="联系失败客户产品交易情况")
    success_customers_prodtxn: WaihuProductTransaction = Field(description="联系成功客户产品交易情况")
    effective_call_customers_prodtxn: WaihuProductTransaction = Field(description="有效通话客户产品交易情况")
    effective_call_prodtop5: WaihuProductTop5 = Field(description="有效通话客户产品交易TOP5")
    effective_call_deposit_source: WaihuFundSource = Field(description="有效通话客户存款购买资金来源")
    effective_call_wealth_source: WaihuFundSource = Field(description="有效通话客户理财购买资金来源")
    all_customers_fund_conversion: WaihuFundConversion = Field(description="外呼所有客户资金转化情况")
    success_customers_fund_conversion: WaihuFundConversion = Field(description="联系成功客户资金转化情况")
    failed_customers_fund_conversion: WaihuFundConversion = Field(description="联系失败客户资金转化情况")
    effective_call_fund_conversion: WaihuFundConversion = Field(description="有效通话客户资金转化情况")


class WaihuActivityDetailResponse(BaseModel):
    """外呼活动详情响应."""

    success: bool = Field(default=True, description="是否成功")
    act_no: str = Field(description="活动编号")
    data: WaihuActivityDetail = Field(description="活动详情数据")


class WaihuActivityListItem(BaseModel):
    """外呼活动列表项."""

    act_no: str = Field(description="活动编号")
    act_name: Optional[str] = Field(default=None, description="活动名称")
    yewu_type: Optional[str] = Field(default=None, description="业务类型")
    活动状态: Optional[str] = Field(default=None, description="活动状态")
    活动人数: Optional[int] = Field(default=None, description="活动人数")


class WaihuActivityListResponse(BaseModel):
    """外呼活动列表响应."""

    total: int = Field(description="总数")
    activities: list[WaihuActivityListItem] = Field(description="活动列表")
