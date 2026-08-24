"""Marketing campaign data loader and search service."""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl

logger = logging.getLogger("mock.campaign")

_EXCEL_PATH: Path = Path(__file__).parent / "清洗后_活动运营数据.xlsx"
_data_cache: list[dict[str, Any]] | None = None


_STRING_FIELDS = {"活动编号", "活动名称", "活动内容", "活动状态", "活动运营目标", "活动类型", "活动渠道", "目标客群"}

_FALLBACK_CAMPAIGNS: list[dict[str, Any]] = [
    {
        "活动编号": "ACT20250612104742",
        "数据日期": date(2025, 6, 30),
        "活动名称": "2025流失客户挽回T1输送_专班",
        "活动开始日期": date(2025, 5, 12),
        "活动结束日期": date(2025, 6, 30),
        "活动内容": "针对流失风险客户进行资产提升和权益触达",
        "活动运营人数": 18600,
        "活动状态": "活动结束",
        "活动运营目标": "促资产提升",
        "活动类型": "促资产提升类型活动",
        "活动渠道": "外呼",
        "目标客群": "流失风险客户",
        "当前AUM时点值": 386000000.0,
        "上月末AUM时点值": 333200000.0,
        "人均aum值": 20752.69,
        "人均aum提升额": 2838.71,
        "价值客户数": 4280,
        "价值客户占比": 0.23,
        "价值客户提升数": 780,
        "转化价值客户数": 960,
        "流失价值客户数": 180,
        "存款余额": 120000000.0,
        "存款余额（非活期）": 88000000.0,
        "人均存款余额": 6451.61,
        "存款人均提升额": 1000.00,
        "理财余额": 150000000.0,
        "上个月理财余额": 128600000.0,
        "人均理财余额": 8064.52,
        "理财人均提升额": 1150.54,
        "基金余额": 28000000.0,
        "人均基金余额提升额": 320.00,
        "金融资产提升额": 52800000.0,
        "存款提升额": 18600000.0,
        "理财提升额": 21400000.0,
        "APP动账活跃提升率": 0.126,
        "人均产品覆盖数": 2.3,
        "人均产品覆盖提升数": 0.4,
        "月活跃客户数（mau)": 9800,
        "月活跃客户数提升数": 1500,
        "价值客户提升率": 0.182,
    },
    {
        "活动编号": "ACT20250512104494",
        "数据日期": date(2025, 5, 31),
        "活动名称": "2025财富客户AUM提升专项活动",
        "活动开始日期": date(2025, 5, 1),
        "活动结束日期": date(2025, 5, 31),
        "活动内容": "面向财富客户推荐理财、基金和存款组合",
        "活动运营人数": 12600,
        "活动状态": "活动结束",
        "活动运营目标": "促AUM提升",
        "活动类型": "促资产提升类型活动",
        "活动渠道": "短信",
        "目标客群": "财富客户",
        "当前AUM时点值": 512000000.0,
        "上月末AUM时点值": 442700000.0,
        "人均aum值": 40634.92,
        "人均aum提升额": 5500.00,
        "价值客户数": 5200,
        "价值客户占比": 0.41,
        "价值客户提升数": 1224,
        "转化价值客户数": 1320,
        "流失价值客户数": 96,
        "存款余额": 185000000.0,
        "存款余额（非活期）": 142000000.0,
        "人均存款余额": 14682.54,
        "存款人均提升额": 1928.57,
        "理财余额": 220000000.0,
        "上个月理财余额": 186200000.0,
        "人均理财余额": 17460.32,
        "理财人均提升额": 2682.54,
        "基金余额": 52000000.0,
        "人均基金余额提升额": 680.00,
        "金融资产提升额": 69300000.0,
        "存款提升额": 24300000.0,
        "理财提升额": 33800000.0,
        "APP动账活跃提升率": 0.184,
        "人均产品覆盖数": 3.4,
        "人均产品覆盖提升数": 0.7,
        "月活跃客户数（mau)": 10400,
        "月活跃客户数提升数": 2100,
        "价值客户提升率": 0.235,
    },
    {
        "活动编号": "ACT20250418103688",
        "数据日期": date(2025, 5, 18),
        "活动名称": "快捷支付绑卡促活活动",
        "活动开始日期": date(2025, 4, 18),
        "活动结束日期": date(2025, 5, 18),
        "活动内容": "提升手机银行快捷支付签约与交易活跃",
        "活动运营人数": 32000,
        "活动状态": "活动结束",
        "活动运营目标": "促活跃提升",
        "活动类型": "促活跃提升类型活动",
        "活动渠道": "短信",
        "目标客群": "低活跃客户",
        "当前AUM时点值": 168000000.0,
        "上月末AUM时点值": 155400000.0,
        "人均aum值": 5250.0,
        "人均aum提升额": 393.75,
        "价值客户数": 2860,
        "价值客户占比": 0.089,
        "价值客户提升数": 520,
        "转化价值客户数": 730,
        "流失价值客户数": 210,
        "存款余额": 86000000.0,
        "存款余额（非活期）": 54000000.0,
        "人均存款余额": 2687.50,
        "存款人均提升额": 262.50,
        "理财余额": 30000000.0,
        "上个月理财余额": 27900000.0,
        "人均理财余额": 937.50,
        "理财人均提升额": 65.63,
        "基金余额": 8000000.0,
        "人均基金余额提升额": 25.00,
        "金融资产提升额": 12600000.0,
        "存款提升额": 8400000.0,
        "理财提升额": 2100000.0,
        "APP动账活跃提升率": 0.236,
        "人均产品覆盖数": 1.8,
        "人均产品覆盖提升数": 0.5,
        "月活跃客户数（mau)": 22400,
        "月活跃客户数提升数": 4600,
        "价值客户提升率": 0.182,
    },
    {
        "活动编号": "ACT20260115123456",
        "数据日期": date(2026, 4, 30),
        "活动名称": "2026春季资产提升专项活动",
        "活动开始日期": date(2026, 2, 1),
        "活动结束日期": date(2026, 4, 30),
        "活动内容": "面向存量客户通过阶梯奖励提升AUM，推荐大额存单、结构性存款和中低风险理财产品",
        "活动运营人数": 25000,
        "活动状态": "活动结束",
        "活动运营目标": "促资产提升",
        "活动类型": "促资产提升类型活动",
        "活动渠道": "外呼",
        "目标客群": "AUM 5万-50万存量客户",
        "当前AUM时点值": 856000000.0,
        "上月末AUM时点值": 747500000.0,
        "人均aum值": 34240.00,
        "人均aum提升额": 8250.50,
        "价值客户数": 7800,
        "价值客户占比": 0.312,
        "价值客户提升数": 2100,
        "转化价值客户数": 1850,
        "流失价值客户数": 230,
        "存款余额": 320000000.0,
        "存款余额（非活期）": 245000000.0,
        "人均存款余额": 12800.00,
        "存款人均提升额": 3200.00,
        "理财余额": 418000000.0,
        "上个月理财余额": 370000000.0,
        "人均理财余额": 16720.00,
        "理财人均提升额": 4100.00,
        "基金余额": 118000000.0,
        "人均基金余额提升额": 950.50,
        "AUM千元以上客户数": 22000,
        "转化AUM千元客户数": 3800,
        "LUM达标客户数": 3500,
        "转化LUM达标客户数": 820,
        "金卡（含）以上客户数": 4200,
        "转化金卡（含）以上客户数": 680,
        "金融资产提升额": 108500000.0,
        "存款提升额": 42000000.0,
        "理财提升额": 48000000.0,
        "APP动账活跃提升率": 0.158,
        "人均产品覆盖数": 2.8,
        "人均产品覆盖提升数": 0.6,
        "月活跃客户数（mau)": 18600,
        "月活跃客户数提升数": 3200,
        "价值客户提升率": 0.269,
    },
    {
        "活动编号": "ACT20260301123457",
        "数据日期": date(2026, 8, 15),
        "活动名称": "2026夏季资产提升_金卡客户权益活动",
        "活动开始日期": date(2026, 5, 15),
        "活动结束日期": date(2026, 8, 15),
        "活动内容": "面向金卡及以上客户推出专属高收益理财、家族信托咨询及机场贵宾厅权益",
        "活动运营人数": 8200,
        "活动状态": "活动结束",
        "活动运营目标": "促资产提升",
        "活动类型": "促资产提升类型活动",
        "活动渠道": "外呼",
        "目标客群": "金卡及以上客户",
        "当前AUM时点值": 920000000.0,
        "上月末AUM时点值": 768000000.0,
        "人均aum值": 112195.12,
        "人均aum提升额": 18600.00,
        "价值客户数": 6500,
        "价值客户占比": 0.793,
        "价值客户提升数": 1200,
        "转化价值客户数": 980,
        "流失价值客户数": 45,
        "存款余额": 280000000.0,
        "存款余额（非活期）": 220000000.0,
        "人均存款余额": 34146.34,
        "存款人均提升额": 5800.00,
        "理财余额": 520000000.0,
        "上个月理财余额": 440000000.0,
        "人均理财余额": 63414.63,
        "理财人均提升额": 9800.00,
        "基金余额": 120000000.0,
        "人均基金余额提升额": 3000.00,
        "AUM千元以上客户数": 8100,
        "转化AUM千元客户数": 650,
        "金卡（含）以上客户数": 8200,
        "转化金卡（含）以上客户数": 320,
        "金融资产提升额": 152000000.0,
        "存款提升额": 48000000.0,
        "理财提升额": 80000000.0,
        "APP动账活跃提升率": 0.213,
        "人均产品覆盖数": 4.2,
        "人均产品覆盖提升数": 0.9,
        "月活跃客户数（mau)": 7200,
        "月活跃客户数提升数": 850,
        "价值客户提升率": 0.185,
    },
    {
        "活动编号": "ACT20260401123458",
        "数据日期": date(2026, 6, 30),
        "活动名称": "2026理财到期客户专属承接活动",
        "活动开始日期": date(2026, 4, 1),
        "活动结束日期": date(2026, 6, 30),
        "活动内容": "针对一季度和二季度理财到期客户，提供专属续接产品推荐和费率优惠，防止资金外流",
        "活动运营人数": 15000,
        "活动状态": "活动结束",
        "活动运营目标": "理财到期承接转化",
        "活动类型": "面向理财到期客户类型活动",
        "活动渠道": "外呼",
        "目标客群": "30天内理财到期客户",
        "当前AUM时点值": 680000000.0,
        "上月末AUM时点值": 698000000.0,
        "人均aum值": 45333.33,
        "人均aum提升额": -1200.00,
        "价值客户数": 5200,
        "价值客户占比": 0.347,
        "价值客户提升数": -180,
        "转化价值客户数": 4100,
        "流失价值客户数": 680,
        "存款余额": 195000000.0,
        "存款余额（非活期）": 148000000.0,
        "人均存款余额": 13000.00,
        "存款人均提升额": -350.00,
        "理财余额": 420000000.0,
        "上个月理财余额": 432800000.0,
        "人均理财余额": 28000.00,
        "理财人均提升额": -850.00,
        "基金余额": 65000000.0,
        "金融资产提升额": -18000000.0,
        "存款提升额": -5200000.0,
        "理财提升额": -12800000.0,
        "APP动账活跃提升率": 0.092,
        "人均产品覆盖数": 3.1,
        "到期理财产品数": 320,
        "到期理财金额": 650000000.0,
        "到期客户数": 15000,
        "到期后转化率": 0.273,
        "到期后再购金额": 178000000.0,
        "到期后再购客户数": 4100,
    },
    {
        "活动编号": "ACT20260701123459",
        "数据日期": date(2026, 8, 21),
        "活动名称": "2026三季度理财到期客户回馈活动",
        "活动开始日期": date(2026, 7, 1),
        "活动结束日期": date(2026, 9, 30),
        "活动内容": "面向三季度理财集中到期客户，定制阶梯式专属利率和积分回馈方案",
        "活动运营人数": 12000,
        "活动状态": "进行中",
        "活动运营目标": "理财到期承接转化",
        "活动类型": "面向理财到期客户类型活动",
        "活动渠道": "短信",
        "目标客群": "60天内理财到期客户",
        "当前AUM时点值": 550000000.0,
        "上月末AUM时点值": 559600000.0,
        "人均aum值": 45833.33,
        "人均aum提升额": -800.00,
        "价值客户数": 3800,
        "价值客户占比": 0.317,
        "价值客户提升数": -120,
        "转化价值客户数": 2900,
        "流失价值客户数": 520,
        "存款余额": 160000000.0,
        "存款余额（非活期）": 122000000.0,
        "人均存款余额": 13333.33,
        "存款人均提升额": -200.00,
        "理财余额": 350000000.0,
        "上个月理财余额": 357200000.0,
        "人均理财余额": 29166.67,
        "理财人均提升额": -600.00,
        "基金余额": 40000000.0,
        "金融资产提升额": -9600000.0,
        "存款提升额": -2400000.0,
        "理财提升额": -7200000.0,
        "APP动账活跃提升率": 0.078,
        "人均产品覆盖数": 2.9,
        "到期理财产品数": 260,
        "到期理财金额": 480000000.0,
        "到期客户数": 12000,
        "到期后转化率": 0.242,
        "到期后再购金额": 116000000.0,
        "到期后再购客户数": 2900,
    },
]


def _serialize_value(value: Any, field_name: str = "") -> Any:
    """Serialize cell values (datetime -> date, clean dirty numeric strings)."""
    if isinstance(value, datetime):
        return value.date()
    if (
        isinstance(value, str)
        and value.strip()
        and field_name not in _STRING_FIELDS
    ):
        # Strip out non-numeric strings that slipped into numeric columns
        try:
            return float(value)
        except ValueError:
            return None
    return value


def _fill_derived_fields(rows: list[dict[str, Any]]) -> None:
    """Fill missing derived fields (上月末AUM, 上个月理财余额) by computation.

    If a record is missing 上月末AUM时点值 but has both 当前AUM时点值 and
    金融资产提升额, derive: 上月末 = 当前 - 提升额.  Same logic for 理财余额.
    """
    for record in rows:
        if record.get("上月末AUM时点值") is None:
            current_aum = record.get("当前AUM时点值")
            increase = record.get("金融资产提升额")
            if isinstance(current_aum, (int, float)) and isinstance(increase, (int, float)):
                record["上月末AUM时点值"] = round(current_aum - increase, 2)
        if record.get("上个月理财余额") is None:
            wealth = record.get("理财余额")
            wealth_inc = record.get("理财提升额")
            if isinstance(wealth, (int, float)) and isinstance(wealth_inc, (int, float)):
                record["上个月理财余额"] = round(wealth - wealth_inc, 2)


def load_data() -> list[dict[str, Any]]:
    """Load campaign data from Excel into memory, merged with fallback campaigns.

    Returns:
        List of dicts where keys are Chinese column names.
    """
    global _data_cache
    if _data_cache is not None:
        return _data_cache

    rows: list[dict[str, Any]] = []

    if _EXCEL_PATH.exists():
        wb = openpyxl.load_workbook(str(_EXCEL_PATH), data_only=True)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]

        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(v is None for v in row):
                continue
            record = {h: _serialize_value(v, h) for h, v in zip(headers, row)}
            rows.append(record)
        logger.info("Loaded %d campaign records from %s", len(rows), _EXCEL_PATH.name)
    else:
        logger.warning("Excel file not found: %s, using fallback campaign data only", _EXCEL_PATH)

    # Merge fallback campaigns (dedup by 活动编号).
    existing_ids = {
        str(r.get("活动编号") or "") for r in rows if r.get("活动编号")
    }
    for fb in _FALLBACK_CAMPAIGNS:
        fb_id = str(fb.get("活动编号") or "")
        if fb_id and fb_id not in existing_ids:
            rows.append(fb)
            existing_ids.add(fb_id)

    if not rows:
        rows = list(_FALLBACK_CAMPAIGNS)

    _fill_derived_fields(rows)

    _data_cache = rows
    logger.info(
        "Total %d campaign records loaded (%d from Excel, %d from fallback)",
        len(rows),
        len(rows) - sum(1 for fb in _FALLBACK_CAMPAIGNS if fb.get("活动编号") in existing_ids),
        sum(1 for fb in _FALLBACK_CAMPAIGNS if fb.get("活动编号") in existing_ids),
    )
    return rows


def reload_data() -> list[dict[str, Any]]:
    """Force reload data from Excel."""
    global _data_cache
    _data_cache = None
    return load_data()


def search_by_name(keyword: str) -> list[dict[str, Any]]:
    """Fuzzy search campaigns by activity name, type, segment (case-insensitive).

    Args:
        keyword: Search keyword, empty string returns all records.

    Returns:
        List of matching campaign records.
    """
    data = load_data()
    if not keyword:
        return data

    kw = keyword.strip().lower()
    results = []
    for record in data:
        name = record.get("活动名称", "")
        act_id = record.get("活动编号", "")
        act_type = record.get("活动类型", "")
        target = record.get("目标客群", "")
        if (
            (name and kw in str(name).lower())
            or (act_id and kw in str(act_id).lower())
            or (act_type and kw in str(act_type).lower())
            or (target and kw in str(target).lower())
        ):
            results.append(record)
    return results


def get_campaign_by_id(activity_id: str) -> dict[str, Any] | None:
    """Get a single campaign by activity ID.

    Args:
        activity_id: The activity ID (活动编号).

    Returns:
        Campaign record or None if not found.
    """
    data = load_data()
    for record in data:
        if record.get("活动编号") == activity_id:
            return record
    return None
