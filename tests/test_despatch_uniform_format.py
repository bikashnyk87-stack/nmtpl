"""Ten independent format/data checks for each of the five client reports."""
from datetime import date
from io import BytesIO
from unittest.mock import patch
import pytest
from openpyxl import load_workbook
from test_despatch_client_templates_dynamic_parties import trip
from app.services import tiom_despatch_client_reports as reports

KINDS=('trip','material','despatch','destination','transporter')

@pytest.fixture(params=KINDS)
def export_pair(request):
    day=date(2026,11,2)
    rows=[trip('SOURCE/1',day),trip('NEW/1',day,'NEW CUSTOMER PRIVATE LIMITED',
          'NEW SIDING','S.Fines(60-62)','NEW TRANSPORTER')]
    with patch.object(reports,'_finish_client_format',lambda *args:None):
        before,old_totals=reports.build_client_workbook(request.param,rows,day,day)
    after,new_totals=reports.build_client_workbook(request.param,rows,day,day)
    old=load_workbook(before);new=load_workbook(after)
    yield request.param,old,new,old_totals,new_totals
    old.close();new.close()


def bounds(kind,ws):
    if kind=='trip':return [(2,ws.max_row,1,16,(2,))]
    if kind!='transporter':
        end={'material':2,'despatch':3,'destination':5}[kind]
        return [(2,ws.max_row,1,ws.max_column,tuple(range(2,end+1)))]
    label=next(c.row for c in ws['B'] if isinstance(c.value,str) and c.value.startswith('CUMULATIVE DISPATCH FOR THE MONTH'))
    return [(4,9,6,10,(4,5,6)),(4,20,12,16,(4,5,6)),
            (24,label-2,2,ws.max_column,(24,25,26,27)),
            (label+1,ws.max_row,2,ws.max_column,tuple(range(label+1,label+5)))]

@pytest.mark.parametrize('check',range(1,11))
def test_ten_format_and_preservation_checks(export_pair,check):
    kind,old,new,old_totals,new_totals=export_pair
    for ws in new:
        cells=[c for t,b,l,r,h in bounds(kind,ws) for row in ws.iter_rows(min_row=t,max_row=b,min_col=l,max_col=r)
               for c in row if c.__class__.__name__!='MergedCell']
        headers=[c for t,b,l,r,h in bounds(kind,ws) for y in h for row in ws.iter_rows(min_row=y,max_row=y,min_col=l,max_col=r)
                 for c in row if c.__class__.__name__!='MergedCell']
        if check==1:assert all(c.font.name=='Calibri' and c.font.sz==12 for c in cells)
        if check==2:assert all(c.font.bold and c.alignment.wrap_text and c.alignment.horizontal=='center' for c in headers)
        if check==3:assert all(all(getattr(c.border,s).style=='thin' for s in ('left','right','top','bottom')) for c in cells)
        if check==4:assert all(c.fill.patternType=='solid' for c in cells)
        if check==5:assert all(ws.row_dimensions[c.row].height>=24 for c in cells)
        if check==6:assert ws.sheet_view.zoomScale==90 and ws.sheet_view.showGridLines is False
        if check==7:
            prior={c.coordinate:c.value for row in old[ws.title] for c in row if c.value is not None}
            now={c.coordinate:c.value for row in ws for c in row if c.value is not None}
            assert prior==now
        if check==8:
            for row in old[ws.title]:
                for c in row:
                    if isinstance(c.value,(int,float)) or (isinstance(c.value,str) and c.value.startswith('=')):
                        assert ws[c.coordinate].number_format==c.number_format
        if check==9:
            assert all(c.fill.fgColor.rgb[-6:]==reports.YELLOW for c in cells if c.font.bold and c not in headers)
        if check==10:
            assert old_totals==new_totals
            assert new_totals['trips']==2 and new_totals['quantityMt']==60.25
