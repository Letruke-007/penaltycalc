from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


# ----------------------------
# Common scalar types
# ----------------------------

DateStr = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{2}\.\d{2}\.\d{4}$",
        strip_whitespace=True,
    ),
]

PeriodStr = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{2}\.\d{4}$",  # MM.YYYY
        strip_whitespace=True,
    ),
]

MoneyStr = Annotated[
    str,
    StringConstraints(
        pattern=r"^-?\d+\.\d{2}$",  # 12345.67, -12345.67
        strip_whitespace=True,
    ),
]


# ----------------------------
# Annual adjustment share marker
# ----------------------------

LineKind = Literal["annual_adjustment_share"]


class AnnualAdjustmentShareFields(BaseModel):
    """
    Optional marker fields for lines belonging to annual adjustment share block.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Optional[LineKind] = Field(default=None)
    adjustment_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    payable_month: Optional[PeriodStr] = Field(default=None)
    base_period: Optional[PeriodStr] = Field(default=None)


# ----------------------------
# Core statement models
# ----------------------------

class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_pdf: str
    generated_at: str  # ISO 8601 UTC


class Debtor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    inn: str


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: str
    date: DateStr


class StatementPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_: DateStr = Field(..., alias="from")
    to: DateStr


class Charge(AnnualAdjustmentShareFields):
    model_config = ConfigDict(extra="forbid")

    period: PeriodStr
    amount: MoneyStr


class Payment(AnnualAdjustmentShareFields):
    """
    v1.2:
      For ordinary payments (kind is absent), 'period' is REQUIRED and means:
      "payment allocated FOR period MM.YYYY", regardless of payment date.

      For annual_adjustment_share payments, period is not required (they are tied by payable_month/base_period).
    """
    model_config = ConfigDict(extra="forbid")

    date: DateStr
    amount: MoneyStr

    # NEW v1.2:
    period: Optional[PeriodStr] = Field(
        default=None,
        description="Allocation period MM.YYYY for ordinary payments (required when kind is None)",
    )

    @model_validator(mode="after")
    def _require_period_for_ordinary(self) -> "Payment":
        if self.kind is None and self.period is None:
            raise ValueError("payments[].period is required for ordinary payments in schema v1.2")
        return self


class Totals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    charged: MoneyStr
    paid: MoneyStr
    debt: MoneyStr


class StatementBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    debtor: Debtor
    contract: Contract
    period: StatementPeriod

    # from UI
    category: Optional[str] = Field(default=None)

    # from UI (must drive B10 and penalty horizon)
    calc_date: DateStr

    # from UI (must drive column J as percent)
    rate_percent: float = Field(..., ge=0)

    # from UI (must drive overdue start in next month)
    overdue_start_day: int | None = Field(
        default=None,
        ge=1,
        le=31,
        description="User-selected day-of-month (1..31) that defines overdue start in next month for each debt period.",
    )
    
    exclude_zero_debt_periods: bool = Field(default=False)

    charges: list[Charge] = Field(default_factory=list)
    payments: list[Payment] = Field(default_factory=list)

    totals: Totals


class Statement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.2"] = "1.2"
    meta: Meta
    statement: StatementBody
