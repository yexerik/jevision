"""Predeclared synthetic fixtures. Labels never depend on Jev responses."""
from pathlib import Path

CHECKS=('clipping','overlap','readability','requirements')


def fixtures():
    rows=[]
    for split in ('calibration','heldout'):
        # Different content, colors, and typography by template group. All viewport
        # variants of one template stay in the same split.
        held=split=='heldout'
        title='Inventory overview' if held else 'Monthly sales'
        table='<table><tr><th>Item</th><th>Total</th></tr><tr><td>Books</td><td>124</td></tr><tr><td>Games</td><td>83</td></tr></table>' if held else '<table><tr><th>Month</th><th>Sales</th></tr><tr><td>April</td><td>240</td></tr><tr><td>May</td><td>310</td></tr></table>'
        base=f'''<!doctype html><html><head><meta charset="utf-8"><style>
        *{{box-sizing:border-box}}body{{margin:0;background:{'#eef5f3' if held else '#f1f4fa'};color:#172638;font:{'18' if held else '20'}px Arial,sans-serif}}
        main{{margin:24px auto;padding:22px;background:white;max-width:900px;width:calc(100% - 32px);border:1px solid #c5cbd1;border-radius:12px}}
        h1{{font-size:28px;margin:0 0 16px}}p{{line-height:1.5}}table{{border-collapse:collapse;width:100%;font-size:18px}}
        td,th{{padding:16px 12px;border:1px solid #65758a;text-align:left}}.region{{position:relative;height:210px;margin-top:20px}}
        .bar{{height:48px;background:#174f93;margin:16px 0;color:white;padding:12px}}.badge{{display:inline-block;background:#174f93;color:white;padding:6px 12px}}
        EXTRA</style></head><body><main><h1>{title}</h1><p>Recent figures for the current reporting period.</p>TABLE DETAIL</main></body></html>'''
        if held:
            # A distinct template family: full-width navigation, two dashboard
            # panels on desktop, stacked panels on mobile, and a dark header.
            base=base.replace('<body><main>', '<body><header style="background:#183c38;color:white;padding:18px 24px;font-size:21px">Northwind · Operations</header><div class="dashboard"><aside><h2>Weekly totals</h2><p>Open orders</p><strong>207</strong></aside><main>')
            base=base.replace('</main></body>', '</main></div></body>')
            base=base.replace('EXTRA', '.dashboard{display:grid;grid-template-columns:210px minmax(0,1fr);gap:24px;max-width:1100px;margin:24px auto;padding:0 16px}aside{padding:22px;background:#d9ece5;border-radius:4px}main{width:100%;margin:0;border-radius:2px}h2{font-size:20px}@media(max-width:600px){.dashboard{grid-template-columns:1fr;gap:16px}aside{padding:12px}aside h2,aside p,aside strong{display:inline-block;margin:0 12px 0 0}} EXTRA')
        cases={
            'clean':('',table,'',{}),
            'clipped-heading':('h1{height:16px;overflow:hidden;white-space:nowrap;font-size:34px}',table,'',{'clipping':True}),
            'overlap':('',table,'<div class="region"><div style="position:absolute;left:0;top:10px;width:100%;padding:15px;background:#ffc;font-size:26px">Order status: awaiting payment</div><div style="position:absolute;left:15px;top:25px;width:90%;padding:15px;background:#eca;font-size:26px">Delivery report: dispatched</div></div>',{'overlap':True}),
            'tiny-text':('td,th{font-size:5px;padding:12px}',table,'',{'readability':True}),
            'low-contrast':('td,th{color:#fafafa;background:#fff;border-color:#ddd}',table,'',{'readability':True}),
            'missing-table':('','<p>No entries available for this period.</p>','',{'requirements':True}),
            'normal-scroll':('',table,'<div style="height:1500px;padding-top:40px;background:linear-gradient(#eef,#fff)">Additional information continues below.</div>',{}),
            'intentional-chart-label':('',table,'<h2>Trend chart</h2><div class="bar" style="width:82%">April: 240</div><div class="bar" style="width:95%">May: 310</div>',{}),
        }
        for name,(css,body,detail,positive) in cases.items():
            # Overlap obscuration is evaluated as overlap only; readability asks
            # about intrinsic typography/contrast, but omit its ambiguous label.
            labels={key:positive.get(key,False) for key in CHECKS}
            if name in ('overlap','clipped-heading'):labels['readability']=None
            if name in ('tiny-text','low-contrast'):labels['requirements']=None
            html=base.replace('EXTRA',css).replace('TABLE',body).replace('DETAIL',detail)
            for viewport,dimensions in [('desktop',(1280,900)),('mobile',(390,844))]:
                rows.append({'id':f'{split}-{name}-{viewport}','group':f'{split}-{name}', 'split':split,'kind':'synthetic','viewport':viewport,'width':dimensions[0],'height':dimensions[1],'expected':'a data table with column headers and two data rows','html':html,'labels':labels})
    return rows


def reference_fixtures(root):
    # Source groups never cross splits. Identity and different-page controls have
    # exact provenance and do not assume source HTML re-renders identically offline.
    pairs={'calibration':[(1,101),(2,102),(3,103),(4,104)],'heldout':[(21,121),(22,122),(23,123),(24,124)]}
    rows=[]
    for split,items in pairs.items():
        for a,b in items:
            for changed in (False,True):
                rows.append({'id':f'{split}-reference-{a:03}-'+('different' if changed else 'same'), 'group':f'{split}-reference-{a:03}', 'split':split, 'kind':'design2code-reference','viewport':'original','expected':'','image':str(root/f'{b if changed else a:03}.png'),'reference':str(root/f'{a:03}.png'),'labels':{'fidelity':changed}})
    return rows


def fresh_overlap_fixtures():
    """Third template family reserved for a new confirmation after V1 inspection."""
    rows=[]
    for case in fixtures():
        if case['split']!='calibration':continue
        case=dict(case)
        case['id']=case['id'].replace('calibration-','confirmation-')
        case['group']=case['group'].replace('calibration-','confirmation-')
        case['split']='heldout';case['labels']={'overlap':case['labels']['overlap']};case['checks']=['overlap']
        html=case['html'].replace('Monthly sales','Conference schedule').replace('Recent figures for the current reporting period.','Select a session and review current availability.').replace('Month','Session').replace('Sales','Seats').replace('April','Keynote').replace('May','Workshop').replace('Order status: awaiting payment','Booking status: awaiting approval').replace('Delivery report: dispatched','Allocation report: confirmed')
        html=html.replace('<body><main>', '<body><nav style="padding:18px 24px;background:#4b2d6b;color:white;font-size:20px">SUMMIT 2026 · Registration</nav><section style="max-width:1000px;margin:24px auto;padding:16px"><label style="display:block;margin-bottom:8px">Search the program</label><div style="display:flex;gap:12px"><input value="Design systems" style="min-width:0;width:65%;font:18px Arial;padding:12px"><button style="padding:12px;font:18px Arial;background:#4b2d6b;color:white">Find sessions</button></div></section><main>')
        html=html.replace('max-width:900px','max-width:1000px').replace('background:#f1f4fa','background:#f7f1fa')
        html=html.replace('</main></body>','</main><footer style="text-align:center;padding:24px;color:#394050">Contact the registration desk for assistance.</footer></body>')
        case['html']=html;rows.append(case)
    # A distinct control collision and an aligned control negative, frozen before
    # observing the refined prompt's outputs on this set.
    base=next(c for c in rows if c['id']=='confirmation-clean-desktop')['html']
    for overlap in (False,True):
        detail='<div style="position:relative;height:150px;margin:20px 0"><label style="position:absolute;left:0;top:20px;font-size:24px">Attendee name and email address</label><input value="Alex Morgan" style="position:absolute;left:25px;top:'+('15' if overlap else '70')+'px;width:200px;padding:14px;font:20px Arial;background:#e7d3f5;border:2px solid #51326b"></div>'
        # Keep the label within the mobile content width to avoid clipping as a confound.
        detail=detail.replace('font-size:24px','font-size:18px').replace('Attendee name and email address','Attendee full name')
        for viewport,width,height in [('desktop',1280,900),('mobile',390,844)]:
            name='control-overlap' if overlap else 'aligned-control'
            rows.append({'id':f'confirmation-{name}-{viewport}','group':f'confirmation-{name}','split':'heldout','kind':'synthetic','viewport':viewport,'width':width,'height':height,'expected':'a data table','html':base.replace('</main>',detail+'</main>'),'labels':{'overlap':overlap},'checks':['overlap']})
    return rows


def overlap_regression_fixtures():
    """Frozen V3 regression set: clipping-only, genuine collisions, and both."""
    rows=[]
    base='''<!doctype html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}body{margin:0;color:#203047;background:#f0f5fa;font:18px Arial}
    header{background:#203d65;color:white;padding:18px 24px;font-size:22px}
    main{max-width:900px;margin:24px auto;padding:24px;width:calc(100% - 32px);background:white;border:1px solid #bbc9d9}
    h1{font-size:30px;line-height:38px;margin:0 0 20px}p{line-height:1.5}
    table{border-collapse:collapse;width:100%;font-size:18px}td,th{padding:12px;border:1px solid #789;text-align:left}
    .region{position:relative;margin:24px 0;height:190px}.one,.two{position:absolute;padding:16px;font-size:24px}
    .one{left:0;top:0;background:#ffe3a4;width:100%}.two{left:16px;top:20px;background:#ddb8ed;width:90%}
    EXTRA</style></head><body><header>Research lab · Results</header><main><h1>Monthly sample analysis</h1><p>Review measurements and approve the summary.</p><table><tr><th>Sample</th><th>Value</th></tr><tr><td>Alpha</td><td>124</td></tr><tr><td>Beta</td><td>83</td></tr></table>DETAIL</main></body></html>'''
    collision='<div class="region"><div class="one">Sample result awaiting approval</div><div class="two">Quality review requires attention</div></div>'
    control='<div class="region"><label style="position:absolute;top:18px;left:0">Reviewer full name</label><input value="Jordan Ellis" style="position:absolute;top:12px;left:28px;width:200px;font:20px Arial;padding:14px;background:#ded4fa;border:2px solid #438"></div>'
    card='<div class="region"><p style="position:absolute;top:10px;left:0;width:100%">Summary notes: All sample results must be reviewed by the laboratory supervisor.</p><div style="position:absolute;top:35px;left:40px;background:#cce0ff;border:2px solid #367;padding:20px;width:75%">Approval panel</div></div>'
    cases={
      'clean':('', '',False,False),
      'vertical-heading-crop':('h1{height:15px;overflow:hidden;white-space:nowrap}', '',False,True),
      'horizontal-heading-crop':('h1{width:120px;overflow:hidden;white-space:nowrap}', '',False,True),
      'multiline-heading-crop':('h1{width:210px;height:46px;overflow:hidden}', '',False,True),
      'clipped-input':('', '<div style="width:120px;overflow:hidden;margin-top:24px"><input value="Reviewer full name" style="width:260px;padding:16px;font:20px Arial"></div>',False,True),
      'text-overlap':('',collision,True,False),
      'control-overlap':('',control,True,False),
      'panel-overlap':('',card,True,False),
      'clipping-with-text-overlap':('h1{height:15px;overflow:hidden;white-space:nowrap}',collision,True,True),
      'clipping-with-control-overlap':('h1{width:120px;overflow:hidden;white-space:nowrap}',control,True,True),
      'clipping-with-panel-overlap':('h1{width:210px;height:46px;overflow:hidden}',card,True,True),
      'intentional-chart-label':('', '<div style="margin-top:24px;background:#255393;padding:14px;color:white;width:85%">Alpha: 124</div>',False,False),
    }
    for name,(css,detail,overlap,clipping) in cases.items():
      for viewport,width,height in [('desktop',1280,900),('mobile',390,844)]:
        rows.append({'id':f'regression-{name}-{viewport}','group':f'regression-{name}','split':'heldout','kind':'synthetic','viewport':viewport,'width':width,'height':height,'expected':'a data table with two sample rows','html':base.replace('EXTRA',css).replace('DETAIL',detail),'labels':{'overlap':overlap,'clipping':clipping},'checks':['overlap','clipping']})
    return rows
