from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator


class WeightFactorIn(BaseModel):
    factorType: str = Field(min_length=1, max_length=50)
    factorValue: Decimal = Field(gt=0)
    factorUnit: str = Field(min_length=1, max_length=30)
    effectiveFrom: date
    effectiveTo: date | None = None
    operatingDate: date | None = None
    shift: str | None = Field(default=None, max_length=20)
    materialId: str | None = Field(default=None, max_length=80)
    vehicleClass: str | None = Field(default=None, max_length=80)
    sourceOrg: str = Field(default="MCL", max_length=80)
    referenceNo: str | None = Field(default=None, max_length=120)
    referenceDate: date | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effectiveTo and self.effectiveTo < self.effectiveFrom:
            raise ValueError("effectiveTo cannot be before effectiveFrom")
        return self


class WeightFactorDecisionIn(BaseModel):
    action: str = Field(pattern=r"^(APPROVE|REJECT)$")
    reason: str | None = Field(default=None, max_length=1000)


class SiteWbManualIn(BaseModel):
    wbId: str = Field(min_length=1, max_length=80)
    weighAt: datetime
    vehicleRegNo: str = Field(min_length=1, max_length=80)
    party: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=160)
    destination: str | None = Field(default=None, max_length=160)
    grossKg: Decimal = Field(gt=0)
    tareKg: Decimal = Field(ge=0)
    netKg: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def validate_weight(self):
        if self.grossKg <= self.tareKg:
            raise ValueError("Gross weight must be greater than Tare weight")
        if self.netKg <= 0:
            raise ValueError("Net weight must be greater than 0")
        if abs((self.grossKg - self.tareKg) - self.netKg) > Decimal("1"):
            raise ValueError("Gross - Tare must equal Net within 1 kg")
        return self


class SiteTripIn(BaseModel):
    eventAt: datetime | None = None
    vehicleId: str | None = Field(default=None, max_length=50)
    vehicleRaw: str | None = Field(default=None, max_length=80)
    driverId: str | None = Field(default=None, max_length=40)
    loadingEquipmentId: str | None = Field(default=None, max_length=50)
    loadingOperatorId: str | None = Field(default=None, max_length=40)
    sourceLocationId: str | None = Field(default=None, max_length=80)
    destinationLocationId: str | None = Field(default=None, max_length=80)
    materialId: str | None = Field(default=None, max_length=80)
    gpNo: str | None = Field(default=None, max_length=80)
    tripSeq: int | None = Field(default=None, ge=1)
    loadingStartAt: datetime | None = None
    loadingEndAt: datetime | None = None
    unloadingStartAt: datetime | None = None
    unloadingEndAt: datetime | None = None
    quantityMt: Decimal | None = Field(default=None, ge=0)
    quantityCum: Decimal | None = Field(default=None, ge=0)
    weightBasis: str | None = Field(default=None, max_length=40)
    factorId: str | None = Field(default=None, max_length=60)
    sourceType: str = Field(default="PORTAL", max_length=40)
    sourceRecordUid: str | None = Field(default=None, max_length=120)


class SiteHsdTransactionIn(BaseModel):
    operatingDate: date
    shift: str | None = Field(default=None, max_length=20)
    transactionType: str = Field(pattern=r"^(OPENING|RECEIPT|ISSUE|ADJUSTMENT)$")
    assetType: str | None = Field(default=None, max_length=40)
    assetId: str | None = Field(default=None, max_length=80)
    litres: Decimal
    supplier: str | None = Field(default=None, max_length=120)
    referenceNo: str | None = Field(default=None, max_length=120)
    meterReading: Decimal | None = None
    eventAt: datetime | None = None
    sourceType: str = Field(default="PORTAL", max_length=40)
    sourceRecordUid: str | None = Field(default=None, max_length=120)


class UserSitePermissionPlanIn(BaseModel):
    sites: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    defaultSite: str | None = None


class UserAccountCreateIn(BaseModel):
    loginId: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    admin: bool = False
    active: bool = True
    sites: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    defaultSite: str | None = None


class UserAccountUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=12, max_length=128)
    admin: bool | None = None
    active: bool | None = None


class SiteAttendanceIn(BaseModel):
    operatingDate: date
    shift: str = Field(min_length=1, max_length=20)
    employeeId: str = Field(min_length=1, max_length=40)
    status: str = Field(default="PRESENT", max_length=20)
    inAt: datetime | None = None
    outAt: datetime | None = None
    workedHours: Decimal | None = Field(default=None, ge=0, le=24)
    sourceType: str = Field(default="PORTAL", max_length=40)
    sourceRecordUid: str | None = Field(default=None, max_length=120)
    remarks: str | None = Field(default=None, max_length=300)


class SiteAssetAttendanceIn(BaseModel):
    operatingDate: date
    shift: str = Field(min_length=1, max_length=20)
    assetId: str = Field(min_length=1, max_length=80)
    status: str = Field(default="RUNNING", max_length=20)
    condition: str | None = Field(default=None, max_length=40)
    remarks: str | None = Field(default=None, max_length=300)


class SiteDeploymentIn(BaseModel):
    operatingDate: date
    shift: str = Field(min_length=1, max_length=20)
    assetId: str | None = Field(default=None, max_length=80)
    employeeId: str | None = Field(default=None, max_length=40)
    locationId: str | None = Field(default=None, max_length=80)
    activity: str | None = Field(default=None, max_length=80)
    fromAt: datetime | None = None
    toAt: datetime | None = None
    status: str = Field(default="ACTIVE", max_length=30)
    remarks: str | None = Field(default=None, max_length=300)


class SiteAssetMeterIn(BaseModel):
    operatingDate: date
    shift: str = Field(min_length=1, max_length=20)
    assetId: str = Field(min_length=1, max_length=80)
    meterType: str = Field(pattern=r"^(HMR|KMR|OTHER)$")
    openingReading: Decimal | None = Field(default=None, ge=0)
    closingReading: Decimal | None = Field(default=None, ge=0)
    sourceType: str = Field(default="PORTAL", max_length=40)
    remarks: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_meter(self):
        if self.openingReading is not None and self.closingReading is not None and self.closingReading < self.openingReading:
            raise ValueError("closingReading cannot be lower than openingReading")
        return self


class SiteSurveyMeasurementIn(BaseModel):
    periodStart: date
    periodEnd: date
    materialId: str | None = Field(default=None, max_length=80)
    measurementType: str = Field(default="MCL_SURVEY", max_length=40)
    measuredCum: Decimal = Field(ge=0)
    measuredMt: Decimal | None = Field(default=None, ge=0)
    sourceOrg: str = Field(default="MCL", max_length=80)
    referenceNo: str | None = Field(default=None, max_length=120)
    referenceDate: date | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_period(self):
        if self.periodEnd < self.periodStart:
            raise ValueError("periodEnd cannot be before periodStart")
        return self


class SiteDecisionIn(BaseModel):
    action: str = Field(pattern=r"^(APPROVE|REJECT|RESOLVE|REOPEN)$")
    reason: str | None = Field(default=None, max_length=1000)


class SiteDataQualityResolveIn(BaseModel):
    resolution: str = Field(min_length=1, max_length=2000)


class SiteMapConfigIn(BaseModel):
    mapUrl: str | None = Field(default=None, max_length=2000)


class SiteSatelliteObservationIn(BaseModel):
    provider: str = Field(default="SENTINEL-2", max_length=40)
    imageDate: date
    cloudPct: Decimal | None = Field(default=None, ge=0, le=100)
    imageRef: str | None = Field(default=None, max_length=4000)
    previousObservationId: str | None = Field(default=None, max_length=60)
    changeAreaHa: Decimal | None = Field(default=None, ge=0)
    status: str = Field(default="AVAILABLE", max_length=30)
    notes: str | None = Field(default=None, max_length=1000)


class TiomMisTripRowIn(BaseModel):
    loadingAt: datetime | None = None
    unloadingAt: datetime | None = None
    material: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=160)
    destination: str | None = Field(default=None, max_length=160)
    remarks: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_times(self):
        if self.loadingAt and self.unloadingAt and self.unloadingAt < self.loadingAt:
            raise ValueError("unloadingAt cannot be before loadingAt")
        return self


class TiomMisReportIn(BaseModel):
    operatingDate: date
    shift: str = Field(min_length=1, max_length=20)
    vehicleId: str = Field(min_length=1, max_length=50)
    operatorId: str | None = Field(default=None, max_length=40)
    openingKmr: Decimal | None = Field(default=None, ge=0)
    closingKmr: Decimal | None = Field(default=None, ge=0)
    openingHmr: Decimal | None = Field(default=None, ge=0)
    closingHmr: Decimal | None = Field(default=None, ge=0)
    paperRef: str | None = Field(default=None, max_length=120)
    sourceDocument: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    rows: list[TiomMisTripRowIn] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_meter_ranges(self):
        if self.openingKmr is not None and self.closingKmr is not None and self.closingKmr < self.openingKmr:
            raise ValueError("closingKmr cannot be lower than openingKmr")
        if self.openingHmr is not None and self.closingHmr is not None and self.closingHmr < self.openingHmr:
            raise ValueError("closingHmr cannot be lower than openingHmr")
        if not self.rows:
            raise ValueError("At least one MIS trip row is required")
        return self
