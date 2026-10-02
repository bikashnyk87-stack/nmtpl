from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator


class BreakdownIn(BaseModel):
    assetId: str = Field(min_length=1, max_length=50)
    problemCategory: str = Field(min_length=1, max_length=80)
    problem: str = Field(min_length=1, max_length=300)
    reportedAt: datetime | None = None
    locationId: str | None = Field(default=None, max_length=80)
    remarks: str | None = Field(default=None, max_length=2000)


class BreakdownCloseIn(BaseModel):
    diagnosis: str | None = Field(default=None, max_length=2000)
    rootCause: str | None = Field(default=None, max_length=2000)
    actionTaken: str = Field(min_length=1, max_length=3000)
    mechanicId: str | None = Field(default=None, max_length=40)
    labourHours: Decimal | None = Field(default=None, ge=0)
    externalCost: Decimal = Field(default=Decimal("0"), ge=0)
    releasedAt: datetime | None = None
    remarks: str | None = Field(default=None, max_length=2000)


class JobCardIn(BaseModel):
    assetId: str = Field(min_length=1, max_length=50)
    jobType: str = Field(min_length=1, max_length=50)
    sourceType: str = Field(default="GENERAL", max_length=30)
    sourceId: str | None = Field(default=None, max_length=70)
    complaint: str | None = Field(default=None, max_length=2000)
    mechanicId: str | None = Field(default=None, max_length=40)
    openedAt: datetime | None = None
    remarks: str | None = Field(default=None, max_length=2000)


class JobCardUpdateIn(BaseModel):
    status: str = Field(pattern=r"^(OPEN|IN_PROGRESS|COMPLETED|RELEASED|CANCELLED)$")
    diagnosis: str | None = Field(default=None, max_length=2000)
    rootCause: str | None = Field(default=None, max_length=2000)
    actionTaken: str | None = Field(default=None, max_length=3000)
    mechanicId: str | None = Field(default=None, max_length=40)
    labourHours: Decimal | None = Field(default=None, ge=0)
    externalCost: Decimal | None = Field(default=None, ge=0)
    remarks: str | None = Field(default=None, max_length=2000)


class ServicePlanIn(BaseModel):
    assetId: str | None = Field(default=None, max_length=50)
    equipmentType: str | None = Field(default=None, max_length=60)
    makeModel: str | None = Field(default=None, max_length=120)
    serviceName: str = Field(min_length=1, max_length=120)
    scheduleBasis: str = Field(pattern=r"^(HMR|KMR|DAYS|MONTHS|WHICHEVER_FIRST)$")
    intervalValue: Decimal | None = Field(default=None, gt=0)
    calendarIntervalDays: int | None = Field(default=None, gt=0)
    warningValue: Decimal | None = Field(default=None, ge=0)
    lastServiceAt: date | None = None
    lastMeter: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_basis(self):
        if self.scheduleBasis in {"HMR", "KMR"} and self.intervalValue is None:
            raise ValueError("intervalValue is required for HMR/KMR schedule")
        if self.scheduleBasis in {"DAYS", "MONTHS"} and self.calendarIntervalDays is None:
            raise ValueError("calendarIntervalDays is required for calendar schedule")
        if self.scheduleBasis == "WHICHEVER_FIRST" and self.intervalValue is None and self.calendarIntervalDays is None:
            raise ValueError("WHICHEVER_FIRST needs a meter or calendar interval")
        return self


class ServiceCompleteIn(BaseModel):
    servicedAt: datetime | None = None
    meterType: str | None = Field(default=None, pattern=r"^(HMR|KMR)$")
    meterReading: Decimal | None = Field(default=None, ge=0)
    jobCardId: str | None = Field(default=None, max_length=70)
    remarks: str | None = Field(default=None, max_length=2000)


class ComponentMasterIn(BaseModel):
    componentName: str = Field(min_length=1, max_length=140)
    category: str | None = Field(default=None, max_length=80)
    partNumber: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="NOS", max_length=30)
    storeItemId: str | None = Field(default=None, max_length=80)


class ComponentScheduleIn(BaseModel):
    componentId: str = Field(min_length=1, max_length=70)
    assetId: str | None = Field(default=None, max_length=50)
    equipmentType: str | None = Field(default=None, max_length=60)
    makeModel: str | None = Field(default=None, max_length=120)
    scheduleBasis: str = Field(pattern=r"^(HMR|KMR|DAYS|MONTHS|WHICHEVER_FIRST)$")
    intervalValue: Decimal | None = Field(default=None, gt=0)
    calendarIntervalDays: int | None = Field(default=None, gt=0)
    warningValue: Decimal | None = Field(default=None, ge=0)
    requiredQty: Decimal = Field(default=Decimal("1"), gt=0)
    lastChangedAt: date | None = None
    lastMeter: Decimal | None = Field(default=None, ge=0)


class ComponentChangeIn(BaseModel):
    changedAt: datetime | None = None
    meterType: str | None = Field(default=None, pattern=r"^(HMR|KMR)$")
    meterReading: Decimal | None = Field(default=None, ge=0)
    quantity: Decimal | None = Field(default=None, gt=0)
    jobCardId: str | None = Field(default=None, max_length=70)
    remarks: str | None = Field(default=None, max_length=2000)


class PmPlanIn(BaseModel):
    assetId: str | None = Field(default=None, max_length=50)
    equipmentType: str | None = Field(default=None, max_length=60)
    activity: str = Field(pattern=r"^(PM|WASHING|GREASING|INSPECTION)$")
    planName: str = Field(min_length=1, max_length=120)
    scheduleBasis: str = Field(pattern=r"^(HMR|KMR|DAYS|MONTHS|WHICHEVER_FIRST)$")
    intervalValue: Decimal | None = Field(default=None, gt=0)
    calendarIntervalDays: int | None = Field(default=None, gt=0)
    warningValue: Decimal | None = Field(default=None, ge=0)
    lastDoneAt: date | None = None
    lastMeter: Decimal | None = Field(default=None, ge=0)
    checklist: list[str] = Field(default_factory=list)


class PmExecutionIn(BaseModel):
    assetId: str = Field(min_length=1, max_length=50)
    activity: str = Field(pattern=r"^(PM|WASHING|GREASING|INSPECTION)$")
    pmPlanId: str | None = Field(default=None, max_length=70)
    completedAt: datetime | None = None
    meterType: str | None = Field(default=None, pattern=r"^(HMR|KMR)$")
    meterReading: Decimal | None = Field(default=None, ge=0)
    result: str = Field(default="COMPLETE", pattern=r"^(COMPLETE|PASS|FAIL)$")
    checklist: dict | list | None = None
    jobCardId: str | None = Field(default=None, max_length=70)
    remarks: str | None = Field(default=None, max_length=2000)


class DefProfileIn(BaseModel):
    assetId: str = Field(min_length=1, max_length=50)
    tankCapacityL: Decimal | None = Field(default=None, gt=0)
    normalIssueQtyL: Decimal | None = Field(default=None, gt=0)
    minimumLevelL: Decimal | None = Field(default=None, ge=0)
    expectedRate: Decimal | None = Field(default=None, ge=0)
    rateBasis: str | None = Field(default=None, pattern=r"^(PER_HOUR|PER_KM|PCT_HSD)$")
    alertLevelL: Decimal | None = Field(default=None, ge=0)


class DefTransactionIn(BaseModel):
    assetId: str = Field(min_length=1, max_length=50)
    quantityL: Decimal = Field(gt=0)
    eventAt: datetime | None = None
    operatorId: str | None = Field(default=None, max_length=40)
    issueReference: str | None = Field(default=None, max_length=120)
    remarks: str | None = Field(default=None, max_length=2000)


class UsageIn(BaseModel):
    assetId: str = Field(min_length=1, max_length=50)
    jobCardId: str | None = Field(default=None, max_length=70)
    description: str = Field(min_length=1, max_length=180)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(default="NOS", max_length=30)
    unitCost: Decimal | None = Field(default=None, ge=0)
    componentId: str | None = Field(default=None, max_length=70)
    storeItemId: str | None = Field(default=None, max_length=80)
    storeIssueReference: str | None = Field(default=None, max_length=100)
    remarks: str | None = Field(default=None, max_length=2000)


class LubricantUsageIn(BaseModel):
    assetId: str = Field(min_length=1, max_length=50)
    jobCardId: str | None = Field(default=None, max_length=70)
    lubricantType: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(default="L", max_length=20)
    unitCost: Decimal | None = Field(default=None, ge=0)
    remarks: str | None = Field(default=None, max_length=2000)


class TyreIn(BaseModel):
    serialNo: str = Field(min_length=1, max_length=100)
    brand: str | None = Field(default=None, max_length=80)
    tyreSize: str | None = Field(default=None, max_length=60)
    purchaseDate: date | None = None
    purchaseCost: Decimal | None = Field(default=None, ge=0)


class TyreFitmentIn(BaseModel):
    tyreId: str = Field(min_length=1, max_length=70)
    assetId: str = Field(min_length=1, max_length=50)
    axle: str | None = Field(default=None, max_length=40)
    position: str | None = Field(default=None, max_length=60)
    fittedAt: datetime | None = None
    fitKmr: Decimal | None = Field(default=None, ge=0)


class TyreRemoveIn(BaseModel):
    removedAt: datetime | None = None
    removalKmr: Decimal | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=160)


class EquipmentDocumentIn(BaseModel):
    assetId: str = Field(min_length=1, max_length=50)
    documentType: str = Field(min_length=1, max_length=50)
    referenceNo: str | None = Field(default=None, max_length=120)
    validFrom: date | None = None
    validTo: date | None = None
    remarks: str | None = Field(default=None, max_length=2000)
