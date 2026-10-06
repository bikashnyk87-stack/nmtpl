from __future__ import annotations

import re
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Equipment, Location, LocationAlias, MaterialAlias, Product,
    WbImportBatch, WbMovement,
)
from app.services.wb_mapping import build_location_resolver, norm_vehicle


def authoritative_wb(db: Session, operating_date, shift: str):
    """Return only the latest CONFIRMED WB batch for a TIOM date/shift.

    This mirrors the dashboard rule so MIS/reporting never sums stale confirmed
    re-uploads together with the active batch.
    """
    batches = list(db.scalars(select(WbImportBatch).where(
        WbImportBatch.operating_date == operating_date,
        WbImportBatch.shift == shift,
        WbImportBatch.status == 'CONFIRMED',
        WbImportBatch.confirmed_at.is_not(None),
    ).order_by(WbImportBatch.confirmed_at.desc())))
    if not batches:
        return None, []
    batch = batches[0]
    rows = list(db.scalars(select(WbMovement).where(
        WbMovement.batch_id == batch.batch_id,
        WbMovement.row_status == 'VALID',
    ).order_by(WbMovement.weigh_at, WbMovement.movement_no)))
    return batch, rows


def _norm(value) -> str:
    return re.sub(r'[^A-Z0-9]+', ' ', str(value or '').upper()).strip()


def vehicle_matches(wb: WbMovement, equipment: Equipment) -> bool:
    candidates = {
        norm_vehicle(wb.vehicle_id), norm_vehicle(wb.vehicle_raw),
    }
    assets = {
        norm_vehicle(equipment.machine_id), norm_vehicle(equipment.vehicle_no),
        norm_vehicle(equipment.door_no),
    }
    candidates.discard(''); assets.discard('')
    return bool(candidates & assets)


def resolve_product_id(db: Session, wb: WbMovement) -> str | None:
    products = list(db.scalars(select(Product).where(Product.active)))
    direct = {}
    for p in products:
        direct[_norm(p.product_id)] = p.product_id
        direct.setdefault(_norm(p.name), p.product_id)
    aliases = {_norm(a.alias): a.product_id for a in db.scalars(select(MaterialAlias).where(MaterialAlias.active))}
    for raw in (wb.material_code, wb.material_name):
        key = _norm(raw)
        if not key:
            continue
        if key in aliases:
            return aliases[key]
        if key in direct:
            return direct[key]
        # Useful but conservative fuzzy fallback for values like "SCREEN FINES".
        hits = {pid for name, pid in direct.items() if name and (name in key or key in name)}
        if len(hits) == 1:
            return next(iter(hits))
    return None


def resolve_location_id(db: Session, raw: str | None, direction: str) -> str | None:
    if not raw:
        return None
    resolver = build_location_resolver(db)
    result = resolver.resolve_raw(raw, direction)
    return result if result and db.get(Location, result) else None


def movement_payload(db: Session, wb: WbMovement) -> dict:
    return {
        'movementKey': wb.movement_key,
        'movementNo': wb.movement_no,
        'vehicle': wb.vehicle_raw,
        'materialRaw': wb.material_name or wb.material_code or '',
        'materialId': resolve_product_id(db, wb) or '',
        'sourceRaw': wb.source_raw or '',
        'sourceLocationId': resolve_location_id(db, wb.source_raw, 'SOURCE') or '',
        'destinationRaw': wb.destination_raw or '',
        'destinationLocationId': resolve_location_id(db, wb.destination_raw, 'DESTINATION') or '',
        'netMt': float((wb.net_kg or Decimal('0')) / Decimal('1000')),
        'weighTime': wb.weigh_at.strftime('%H:%M') if wb.weigh_at else '',
    }


def _is_stack(text: str) -> bool:
    t = _norm(text)
    return ('STACK' in t or 'STOCK' in t or bool(re.search(r'(^| )S ?\d+( |$)', t)))


def wb_report_contributions(wb: WbMovement):
    """Map one confirmed WB movement to management-report fact(s).

    OB/WASTE is intentionally excluded: TIOM business rule says OB is a
    trip-factor quantity (currently 40 MT/trip), not a WB quantity.
    A single movement can legitimately feed more than one report fact, e.g.
    screen fines produced and the same tonnes shifted to stack.
    """
    qty = (wb.net_kg or Decimal('0')) / Decimal('1000')
    if qty <= 0:
        return []
    mat = _norm(' '.join([wb.material_code or '', wb.material_name or '']))
    src = _norm(wb.source_raw)
    dst = _norm(wb.destination_raw)
    out: list[tuple[str, Decimal]] = []

    # Explicitly keep OB/WASTE on the trip-factor side.
    if re.search(r'(^| )(OB|WASTE)( |$)', mat):
        return []

    # Rehandling must never become fresh production.  Stock/stack sources and
    # the Project Area fines source are physical movements of already produced
    # material.  They may still be plant feed when they enter a plant.
    project_source = 'FINE' in mat and (('PROJECT' in src and 'FINE' in src) or (bool(re.search(r'(^| )PA( |$)', src)) and 'FINE' in src))
    stock_source = _is_stack(src)
    if 'FINE' in mat and project_source:
        return [('PROJECT_AREA_FINES_TO_STACK', qty), ('PRODUCT_REHANDLED', qty), ('SCREEN_FINES_SHIFTED', qty)]

    if 'UNSCREEN' in mat and ('5 18' in mat or '5-18' in str(wb.material_name or '')):
        return [('UNSCREENED_5_18', qty)]

    # TIOM business rule: CLO 10-40 is COMPANY OLD STOCK used as a quality
    # blending stream. It is not NMTPL fresh production even if a WB source
    # label happens to mention an MSP. When it enters the crusher it remains
    # physical crusher feed but is tagged separately so its share can be
    # excluded from fresh-production accounting.
    raw_name = str(wb.material_name or '').upper()
    is_clo = bool(re.search(r'(^| )CLO( |$)', mat))
    is_10_40 = ('10 40' in mat or '10-40' in raw_name)
    if is_clo and is_10_40:
        out.extend([
            ('PRODUCT_REHANDLED', qty),
            ('OLD_STOCK_BLEND_10_40', qty),
        ])
        if 'CRUSH' in dst or 'OCP' in dst:
            out.extend([
                ('CRUSHER_BLEND_FEED', qty),
                ('CRUSHER_FEED', qty),
            ])
        return out

    # 5-18 products. Source/material suffix decides Screen vs Crusher;
    # CLO by itself must never imply Crusher.
    is_5_18 = ('5 18' in mat or '5-18' in raw_name)
    if is_5_18:
        if stock_source or project_source:
            out.append(('PRODUCT_REHANDLED', qty))
            if 'CRUSH' in dst or 'OCP' in dst:
                out.append(('CRUSHER_FEED', qty))
            return out
        crusher_origin = ('CRUSH' in src or 'OCP' in src or 'CRUS' in mat)
        if crusher_origin:
            out.append(('CRUSHER_5_18', qty))
        elif 'RE SCREEN' in src or 'RESCREEN' in src:
            out.append(('RE_SCREEN_5_18', qty))
        else:
            out.append(('SCREEN_5_18', qty))
        if _is_stack(dst):
            out.append(('SC_5_18_SHIFTED', qty))
        return out

    # Fines products.
    if 'FINE' in mat:
        if stock_source or project_source:
            out.append(('PRODUCT_REHANDLED', qty))
            if 'CRUSH' in dst or 'OCP' in dst:
                out.append(('CRUSHER_FEED', qty))
            return out
        if 'CRUSH' in src or 'OCP' in src:
            out.append(('CRUSHER_FINES', qty))
            if _is_stack(dst):
                out.append(('CRUSHER_FINES_SHIFTED', qty))
        elif 'RE SCREEN' in src or 'RESCREEN' in src:
            out.append(('RE_SCREEN_FINES', qty))
        else:
            out.append(('SCREEN_FINES', qty))
            if _is_stack(dst):
                out.append(('SCREEN_FINES_SHIFTED', qty))
        return out

    if 'LUMP' in mat:
        # Keep raw ROM lumps from mine/excavation separate from screen output.
        mine_source = any(x in src for x in ('HA','RL','QUARRY','PIT','MINE')) and not any(x in src for x in ('MSP','SCREEN','PLANT','STOCK'))
        if 'ROM' in mat and mine_source:
            return [('ROM_LUMPS', qty)]
        if stock_source and ('CRUSH' in dst or 'OCP' in dst):
            return [('PRODUCT_REHANDLED', qty), ('LUMPS_TO_CRUSHER_FROM_STOCK', qty), ('CRUSHER_FEED', qty)]
        if 'CRUSH' in dst or 'OCP' in dst:
            return [('LUMPS_FROM_SCREEN', qty), ('LUMPS_FEED_TO_CRUSHER', qty), ('CRUSHER_FEED', qty)]
        return [('LUMPS_FROM_SCREEN', qty)]

    if 'SUBGRADE' in mat or re.search(r'(^| )SG( |$)', mat):
        return [('SUBGRADE_FEED_PLANT' if any(x in dst for x in ('FEED','PLANT','MSP')) else 'SUBGRADE_DUMP', qty)]

    if 'ROM' in mat:
        # Fresh ROM is counted once at its mine-origin movement regardless of
        # whether it goes directly to a plant or first to ROM stock.
        # ROM leaving stock is rehandling: it can be physical plant feed but
        # must never increase the fresh-ROM production base.
        if stock_source:
            out.append(('ROM_REHANDLED', qty))
            if any(x in dst for x in ('PLANT','FEED','MSP','SCREEN')):
                out.extend([('ROM_STOCK_TO_PLANT_FEED', qty), ('MSP_FEED', qty)])
            elif _is_stack(dst):
                out.append(('ROM_STOCK_TO_STOCK', qty))
            return out
        out.append(('ROM', qty))
        if any(x in dst for x in ('PLANT','FEED','MSP','SCREEN')):
            out.append(('MSP_FEED', qty))
        if _is_stack(dst):
            out.append(('ROM_STOCK_YARD', qty))
        return out

    if 'SPILL' in mat or 'SPILL' in dst:
        # Spillage is either internal recycle, crusher feed, or WIP.
        if 'CRUSH' in dst or 'OCP' in dst:
            return [('SPILLAGE_TO_CRUSHER', qty), ('CRUSHER_FEED', qty)]
        if any(x in dst for x in ('MSP', 'SCREEN')):
            return [('SPILLAGE_RECYCLE_MSP', qty)]
        return [('SPILLAGE_WIP', qty)]

    if '5 40' in mat or '5-40' in str(wb.material_name or ''):
        if 'TANKURA' in dst:
            return [('SHIFT_5_40_TANKURA', qty)]

    return []

def allocate_blended_crusher_output(gross_output, total_feed, blend_feed):
    """Allocate mixed crusher output between fresh feed and old-stock blend.

    Crusher products are physically mixed after processing, so exact tonnes
    cannot be traced back to each feed stream from WB alone. Management
    accounting therefore allocates gross output pro-rata to fresh vs blend
    feed. This preserves actual crusher recovery while preventing old stock
    from inflating fresh production.
    """
    gross = Decimal(str(gross_output or 0))
    feed = Decimal(str(total_feed or 0))
    blend = Decimal(str(blend_feed or 0))
    if gross <= 0:
        return Decimal('0'), Decimal('0')
    if feed <= 0:
        return gross, Decimal('0')
    if blend < 0:
        blend = Decimal('0')
    if blend > feed:
        blend = feed
    blend_output = gross * blend / feed
    fresh_output = gross - blend_output
    return fresh_output, blend_output
