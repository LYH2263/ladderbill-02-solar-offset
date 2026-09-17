"""Solar offset module（光伏电量抵扣）。

- 按户号 + 账期录入发电量抵扣，支持显式版本号更正、旧版只读保留；
- 计费顺序：先扣抵扣（净电量下限零）→ 净电量阶梯分段 → 最后套尖峰系数；
- 提供不落库、不写运行记录的预览接口。
"""

from app.modules.solar_offset.engine import bill_with_offset, deduct
from app.modules.solar_offset.exceptions import AccountNotFound, OffsetConflict
from app.modules.solar_offset.router import router

__all__ = [
    "router",
    "bill_with_offset",
    "deduct",
    "AccountNotFound",
    "OffsetConflict",
]
