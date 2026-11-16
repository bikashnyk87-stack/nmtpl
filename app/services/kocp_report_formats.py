"""September-style KOCP MIS Excel views; read-only, master-based."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy import select
from app.models import Equipment
from app.site_models import SiteTrip, SiteHsdTransaction, SiteAssetMeter
from app.services.kocp_equipment import kocp_equipment_category, kocp_ownership_category


def build(db,start:date,end:date,kind="ALL"):
    kind=kind.upper()
    if kind not in ("ALL","TIPPER","EXCAVATOR","LOADER"):raise HTTPException(422,"Unknown KOCP report format")
    if end<start or (end-start).days>366:raise HTTPException(422,"Invalid report range: maximum 367 days")
    trips=list(db.scalars(select(SiteTrip).where(SiteTrip.site_id=="KOCP",
        SiteTrip.operating_date>=start,SiteTrip.operating_date<=end,
        SiteTrip.status=="POSTED").order_by(SiteTrip.operating_date,SiteTrip.shift,SiteTrip.trip_id)))
    meters=list(db.scalars(select(SiteAssetMeter).where(SiteAssetMeter.site_id=="KOCP",
        SiteAssetMeter.operating_date>=start,SiteAssetMeter.operating_date<=end,
        SiteAssetMeter.meter_type.in_(["HMR","KMR"]))))
    fuel=list(db.scalars(select(SiteHsdTransaction).where(SiteHsdTransaction.site_id=="KOCP",
        SiteHsdTransaction.status=="POSTED",SiteHsdTransaction.transaction_type=="ISSUE",
        SiteHsdTransaction.operating_date>=start,SiteHsdTransaction.operating_date<=end)))
    ids={x for t in trips for x in (t.vehicle_id,t.loading_equipment_id) if x}
    ids.update(m.asset_id for m in meters if m.asset_id)
    ids.update(h.asset_id for h in fuel if h.asset_id)
    eq={e.machine_id:e for e in db.scalars(select(Equipment).where(Equipment.machine_id.in_(ids)))} if ids else {}
    def category(i):
        e=eq.get(i)
        return kocp_equipment_category(e.type,e.make_model) if e else "UNMAPPED"
    def label(i):
        e=eq.get(i)
        return " · ".join(str(x) for x in (f"Door {e.door_no}" if e and e.door_no else None,
              e.vehicle_no if e else None) if x) if e else i or ""
    def owner(i):
        e=eq.get(i)
        return kocp_ownership_category(e.ownership) if e else "UNMAPPED"
    def numeric(x):return Decimal(str(x or 0))
    def value(x):return float(x) if x is not None else None
    def ratio(a,b):return round(float(a/b),3) if a is not None and b is not None and b>0 else None
    # Source truth: one group per equipment/date/shift. Fuel & HMR are not
    # joined to trip rows (which could otherwise multiply these amounts).
    production=defaultdict(lambda:{"trips":0,"mt":Decimal(0),"cum":Decimal(0),"has_mt":False,"has_cum":False,"kinds":set()})
    for t in trips:
        movement="OB" if t.source_type=="SHIFT_OB_CARD" or t.quantity_cum is not None else (
                 "COAL" if t.source_type=="SHIFT_COAL_REGISTER" or t.quantity_mt is not None else "UNKNOWN")
        for role,ident in (("TIPPER",t.vehicle_id),("LOADING",t.loading_equipment_id)):
            if not ident:continue
            physical=category(ident)
            if role=="TIPPER" and physical!="TIPPER":continue
            if role=="LOADING" and physical not in ("EXCAVATOR","LOADER"):continue
            x=production[(t.operating_date,t.shift,ident)]
            x["trips"]+=int(t.trip_count or 0);x["kinds"].add(movement)
            for fld,src in (("mt",t.quantity_mt),("cum",t.quantity_cum)):
                if src is not None:x[fld]+=numeric(src);x["has_"+fld]=True
    hsd=defaultdict(lambda:Decimal(0))
    for f in fuel:
        if f.asset_id:hsd[(f.operating_date,f.shift,f.asset_id)]+=numeric(f.litres)
    readings=defaultdict(dict)
    for m in meters:
        if m.usage is not None:readings[(m.operating_date,m.shift,m.asset_id)][m.meter_type]=numeric(m.usage)
    wb=Workbook();guide=wb.active;guide.title="README"
    for row in (["NMTPL KOCP — SEPTEMBER REPORT FORMAT"],["Date from",start,"Date to",end,"Layout",kind],
        ["Source","Posted KOCP production + ERP equipment + posted HSD + HMR/KMR"],
        ["Control","Unverified paper cards excluded; missing quantity or meters remain BLANK"],
        ["Units","Coal MT and OB CuM are not added; efficiency ratios use their respective units"],
        ["Report history","Only selected period is included; previous cumulative not invented"],
        ["Original templates","Layouts adapted from Sep-2026 supplied workbooks; their #REF errors are not copied"]):
        guide.append(row)
    guide.column_dimensions["A"].width=37;guide.column_dimensions["B"].width=91
    guide["A1"].font=Font(bold=True,color="114B5F",size=15)
    def sheet(name,title,headers,rows):
        ws=wb.create_sheet(name);ws.append([title]);ws.append(["Operating "+str(start)+" to "+str(end)+" | Blank = no source reading/approved quantity"])
        ws.append(headers)
        ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers))
        ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=len(headers))
        ws["A1"].font=Font(bold=True,size=14,color="FFFFFF")
        ws["A1"].fill=PatternFill("solid",fgColor="114B5F")
        ws["A2"].font=Font(italic=True,color="456374")
        for c in ws[3]:
            c.fill=PatternFill("solid",fgColor="D6EDF0");c.font=Font(bold=True)
            c.alignment=Alignment(wrap_text=True)
        ws.row_dimensions[1].height=26;ws.row_dimensions[3].height=32
        ws.freeze_panes="D4";ws.sheet_view.showGridLines=False
        count=0
        for row in rows:
            ws.append(["'"+x if isinstance(x,str) and x.startswith(("=","+","-","@")) else x for x in row]);count+=1
        if not count:ws.append(["No posted source data for this report"])
        ws.auto_filter.ref=f"A3:{ws.cell(row=3,column=len(headers)).column_letter}{max(4,ws.max_row)}"
        for i,h in enumerate(headers,1):
            ws.column_dimensions[ws.cell(row=3,column=i).column_letter].width=min(35,max(12,len(h)+3))
        return ws
    def metrics(keys,unit):
        entries=[production[x] for x in keys]
        count=sum(v["trips"] for v in entries)
        known=any(v["has_"+unit] for v in entries)
        qty=sum((v[unit] for v in entries),Decimal(0)) if known else None
        fuel_ok=bool(keys) and all(k in hsd for k in keys)
        fuel_l=sum((hsd[k] for k in keys),Decimal(0)) if fuel_ok else None
        hours=[readings.get(k,{}).get("HMR") for k in keys]
        kms=[readings.get(k,{}).get("KMR") for k in keys]
        hr=sum(hours,Decimal(0)) if hours and all(x is not None for x in hours) else None
        km=sum(kms,Decimal(0)) if kms and all(x is not None for x in kms) else None
        return [count,value(qty),value(hr),value(km),value(fuel_l),ratio(qty,Decimal(count)),
                ratio(qty,hr),ratio(fuel_l,Decimal(count)),ratio(fuel_l,qty),ratio(fuel_l,hr),ratio(km,fuel_l)]
    def grouped(cls,required=None):
        out=defaultdict(list)
        for k,x in production.items():
            if category(k[2])==cls and (not required or required in x["kinds"]):
                out[(k[0],k[2])].append(k)
        return out
    def daily(cls,unit,required):
        allgroups=grouped(cls,required)
        result=[];cumulative=defaultdict(list)
        for (day,ident),keys in sorted(allgroups.items()):
            cumulative[ident].extend(keys)
            shift=[]
            for sh in ("A","B","C"):
                subset=[k for k in keys if k[1]==sh]
                m=metrics(subset,unit) if subset else None
                shift.extend([m[0] if m else None,m[1] if m else None])
            m=metrics(keys,unit)
            result.append([day,ident,label(ident),owner(ident),*shift,*m])
        totals=[[ident,label(ident),owner(ident),*metrics(keys,unit)]
                for ident,keys in sorted(cumulative.items())]
        return result,totals
    daily_head=["Date","Equipment ID","Door / Machine","Ownership","A Trips","A Qty",
                "B Trips","B Qty","C Trips","C Qty","Total Trips","Qty",
                "HMR Hours","KMR km","HSD L","Factor Qty/Trip","Productivity Qty/Hr",
                "L/Trip","L/Qty","L/Hr","KMPL"]
    cumulative_head=["Equipment ID","Door / Machine","Ownership","Trips","Qty","HMR Hours",
                     "KMR km","HSD L","Factor Qty/Trip","Productivity Qty/Hr","L/Trip","L/Qty","L/Hr","KMPL"]
    if kind in ("ALL","TIPPER"):
        day,totals=daily("TIPPER","cum","OB")
        sheet("OB TIPPER DAILY","KOCP OB TIPPER — DAILY / A B C SHIFTS",daily_head,day)
        sheet("OB TIPPER CONSOLIDATED","OB TIPPER CUMULATIVE — SELECTED PERIOD",cumulative_head,totals)
    if kind in ("ALL","EXCAVATOR"):
        day,totals=daily("EXCAVATOR","cum",None)
        sheet("EXCAVATOR DATE WISE","EXCAVATOR — DATE WISE / A B C SHIFTS",daily_head,day)
        sheet("EXCAVATOR SUMMARY","EXCAVATOR — MONTHLY CUMULATIVE",cumulative_head,totals)
        matrix=((t.operating_date,t.shift,t.vehicle_id,label(t.vehicle_id),
                 t.loading_equipment_id,label(t.loading_equipment_id),t.trip_count,
                 value(t.quantity_mt),value(t.quantity_cum)) for t in trips
                if t.loading_equipment_id and category(t.loading_equipment_id)=="EXCAVATOR")
        sheet("EXCAVATOR TRIP DATABASE","TIPPER WISE / EXCAVATOR WISE TRIPS",
              ["Date","Shift","Tipper ID","Tipper","Excavator ID","Excavator","Trips","Coal MT","OB CuM"],matrix)
        hm=((m.operating_date,m.shift,m.asset_id,label(m.asset_id),m.meter_type,
             value(m.opening_reading),value(m.closing_reading),value(m.usage)) for m in meters
            if category(m.asset_id)=="EXCAVATOR")
        sheet("EXCAVATOR HMR DATABASE","EXCAVATOR HMR DATABASE — SHIFT WISE",
              ["Date","Shift","Excavator ID","Excavator","Meter","Opening","Closing","Usage"],hm)
    if kind in ("ALL","LOADER"):
        day,totals=daily("LOADER","mt",None)
        sheet("LOADER DAILY","LOADER PERFORMANCE — DATE WISE / A B C SHIFTS",daily_head,day)
        sheet("LOADER CUMULATIVE","LOADER — MONTHLY / YEARLY SELECTED PERIOD",cumulative_head,totals)
        sheet("OTHER PARTY LOADER","OTHER PARTY / HIRED LOADER PERFORMANCE",cumulative_head,
              (r for r in totals if r[2] in ("HIRED","THIRD PARTY")))
    stream=BytesIO();wb.save(stream);stream.seek(0)
    return StreamingResponse(stream,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         headers={"Content-Disposition":f'attachment; filename="KOCP_{kind}_SEPT_STYLE_{start}_to_{end}.xlsx"'})
