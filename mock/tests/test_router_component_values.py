"""模板详情 mock 多活动板块应按请求的 actNos 返回真实活动名。

回归测试：之前 `/component-values` 直接返回样例报文，多活动对比板块
（plateTypeCd == "4"）的 resData 硬编码了“演示银行App6月促活营销”和
“五一节前理财营销”，导致报告里出现与用户所选活动不符的活动名。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import router  # noqa: E402

DEMO_NAMES = {"演示银行App6月促活营销", "五一节前理财营销"}


def _multi_activity_plates(plates: list[dict]) -> list[dict]:
    return [p for p in plates if str(p.get("plateTypeCd") or "") == "4"]


def _resdata_act_names(plates: list[dict]) -> set[str]:
    names: set[str] = set()
    for plate in plates:
        for indicator in plate.get("plateShowIndCfgInfDtoList") or []:
            for row in indicator.get("resData") or []:
                name = row.get("actName")
                if name:
                    names.add(str(name))
    return names


def test_multi_activity_plate_uses_requested_campaigns():
    act_nos = ["PV10160182026052830841", "PV10156692026050632065"]
    plates = router._build_template_detail_payload(
        proj_no="XMDHD202605191506594339",
        act_nos=act_nos,
        etl_dt_start="",
        etl_dt_end="",
    )

    multi_plates = _multi_activity_plates(plates)
    assert multi_plates, "样例报文中应存在多活动对比板块"

    names = _resdata_act_names(multi_plates)
    assert "个养开户营销-新城支行" in names
    assert "个养缴存营销-常青支行" in names
    assert not (names & DEMO_NAMES), f"不应再出现样例演示活动名: {names & DEMO_NAMES}"

    # 每个请求的活动编号都应出现在 resData 中
    act_ids = set()
    for plate in multi_plates:
        for indicator in plate.get("plateShowIndCfgInfDtoList") or []:
            for row in indicator.get("resData") or []:
                if row.get("act_no"):
                    act_ids.add(str(row["act_no"]))
    assert act_ids == set(act_nos)


def test_multi_activity_plate_unknown_act_no_falls_back_without_demo_names():
    plates = router._build_template_detail_payload(
        proj_no="XMDHD202605191506594339",
        act_nos=["PV99999999999999999999"],
        etl_dt_start="",
        etl_dt_end="",
    )
    names = _resdata_act_names(_multi_activity_plates(plates))
    assert not (names & DEMO_NAMES)
    assert names, "未知活动也应生成兜底名称"
