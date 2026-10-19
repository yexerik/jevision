"""Browser integration of tool modules with deterministic API responses.

Exercises real rendering, image preparation, events, and V1–V6 routing without
network/API charges. JEV_UI_TEST_ROOT=dist also checks a production build.
"""
from email.parser import BytesParser
from email.policy import default
import io
import json
import mimetypes
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
import unittest

from PIL import Image
from playwright.sync_api import sync_playwright
from scripts.frontend_modules import freeze_modules
from scripts.benchmark_find import benchmark_source

ROOT=Path(__file__).resolve().parents[1]


class ToolModuleBrowserTests(unittest.TestCase):
    def test_routes_controls_and_inference_for_all_tools(self):
        web=ROOT/os.environ.get('JEV_UI_TEST_ROOT','web')
        buffer=io.BytesIO()
        Image.new('RGB',(600,600),'white').save(buffer,format='PNG')
        png=buffer.getvalue()
        dataset={'id':'module-fixture','name':'Module fixture','target':'dogs','createdAt':0,'storage':'workspace',
                 'images':[{'id':f'image-{i}','path':f'photo-{i}.png','name':f'photo-{i}.png','url':'/fixture.png','results':[]} for i in range(2)]}
        requests=[];errors=[];unexpected=[];saved=[];pending_api=[];hold_next=[False]
        def serve(route):
            request=route.request
            url=urlsplit(request.url)
            path=url.path
            if url.netloc!='jev-tools.test':
                route.abort();return
            payload=None
            if path=='/api/library':payload={'datasets':[dataset]}
            elif path=='/api/health':payload={'ok':True,'apiKeyConfigured':True}
            elif path=='/api/design2code/examples':payload={'examples':[{'id':'001'}]}
            elif path=='/api/design2code/status':payload={'status':'complete','message':'Fixture ready'}
            elif path=='/api/design2code/html':payload={'html':'<h1>Module fixture</h1>'}
            elif path=='/api/dataset-settings':
                saved.append(request.post_data_json);payload={'ok':True}
            elif path in ['/fixture.png','/api/design2code/image','/api/render-html']:
                route.fulfill(body=png,content_type='image/png');return
            elif path in ['/api/system-one','/api/count-cars']:
                message=BytesParser(policy=default).parsebytes(
                    ('Content-Type: '+request.headers['content-type']+'\r\n\r\n').encode()+request.post_data_buffer)
                parts=list(message.iter_parts())
                judgment=json.loads(next(part.get_payload(decode=True) for part in parts if part.get_param('name',header='content-disposition')=='request'))
                self.assertGreater(len(parts),1)
                requests.append((path,judgment))
                answers={}
                for key,question in judgment['questions'].items():
                    if question['type']=='choice':
                        choice='2' if key=='object_count' else 'neither' if key=='overlap' else 'one' if key=='r0_multiplicity' or (key=='r0_count' and len(judgment['assets'])==6) else 'none'
                        answers[key]={'type':'choice','choice':choice,'confidence':.99,
                                      'probabilities':{option:1 if option==choice else 0 for option in question['criteria']}}
                    elif question['type']=='box':
                        answers[key]={'type':'box','confidence':.99,'box':{'left':.2,'top':.2,'right':.6,'bottom':.6}}
                    else:
                        answers[key]={'type':'noul','noul':.95 if key=='target_visible' or key.endswith('_presence') else .8 if key.startswith('match_') else .02}
                payload={'model':judgment['model'],'answers':answers,'usage':{'input_tokens':100,'output_tokens':10}}
            elif path.startswith('/api/'):
                unexpected.append(path);route.fulfill(status=500,json={'error':'Unexpected test API'});return
            if payload is not None:
                if path=="/api/system-one" and hold_next[0]:
                    hold_next[0]=False;pending_api.append((route,payload));return
                route.fulfill(json=payload);return
            file=web/path.lstrip('/')
            if not file.is_file():
                if path=='/' or path.startswith('/tools/'):
                    file=web/'index.html'
                else:
                    unexpected.append(path);route.fulfill(status=404,body='Missing test asset');return
            route.fulfill(body=file.read_bytes(),content_type=mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':1440,'height':1100})
                page.route('**/*',serve)
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://jev-tools.test/tools/count')
                page.wait_for_function("document.querySelector('#datasetSelect').options.length===2")
                page.locator('#datasetSelect').select_option(dataset['id'])
                page.wait_for_function("!document.querySelector('#resultCard').classList.contains('hidden')")
                self.assertIn('2',page.locator('#resultCard .result-count').inner_text())
                page.wait_for_function("!document.querySelector('#countButton').disabled")
                self.assertTrue(saved,'Count result was not persisted')
                self.assertEqual(saved[-1]['images'][0]['path'],'photo-0.png')
                self.assertNotIn('name',saved[-1])
                self.assertNotIn('target',saved[-1])
                page.locator('[data-view="find"]').first.click()
                self.assertEqual(urlsplit(page.url).path,'/tools/find')
                self.assertEqual(page.locator('#findModeSelect').input_value(),'all')
                self.assertEqual(page.locator('#findVersionSelect').input_value(),'v6')
                self.assertTrue(page.locator('#findV6Settings').is_visible())
                page.locator('#findDatasetSelect').select_option(dataset['id'])
                prompt_details=page.locator('#findPromptDetails')
                self.assertFalse(prompt_details.evaluate('e=>e.open'))
                self.assertFalse(page.locator('#findQuestionText').is_visible())
                self.assertFalse(page.locator('#findVersionSummary').is_visible())
                prompt_details.locator('summary').click()
                self.assertTrue(page.locator('#findQuestionText').is_visible())
                self.assertIn('dogs',page.locator('#findQuestionText').inner_text())
                prompt_details.locator('summary').press('Space')
                self.assertFalse(page.locator('#findQuestionText').is_visible())
                page.locator('#findObjectButton').click()
                page.wait_for_function("!document.querySelector('#findObjectButton').disabled")
                self.assertEqual(page.locator('.object-detection-box').count(),1)
                self.assertTrue(page.locator('#findObjectStatus').inner_text().startswith('V6 experimental'))
                self.assertEqual(json.loads(page.locator('#findRunConfigData').text_content())['minV3BoxCheckProbability'],.65)
                self.assertFalse(prompt_details.evaluate('e=>e.open'))
                # Locate one remains available as an explicit choice.
                page.locator('#findModeSelect').select_option('one')
                self.assertFalse(page.locator('#findV6Settings').is_visible())
                page.locator('#findObjectButton').click()
                page.wait_for_function("!document.querySelector('#findObjectButton').disabled")
                self.assertEqual(page.locator('.object-detection-box').count(),1)
                page.locator('#findModeSelect').select_option('all')
                self.assertEqual(page.locator('#findVersionSelect').input_value(),'v6')
                self.assertTrue(page.locator('#findV6Settings').is_visible())
                self.assertIn('Default',page.locator('#findVersionSelect option[value=v6]').inner_text())
                self.assertIn('Experimental',page.locator('#findVersionSelect option[value=v5]').inner_text())
                self.assertIn('Experimental',page.locator('#findVersionSelect option[value=v6]').inner_text())
                for version in ['v6','v1','v2','v3','v4','v5']:
                    if version!='v6':page.locator('#findVersionSelect').select_option(version)
                    page.locator('#findObjectButton').click()
                    page.wait_for_function("!document.querySelector('#findObjectButton').disabled")
                    self.assertFalse(page.locator('#findObjectStatus').evaluate("e=>e.classList.contains('error')"),version)
                    self.assertEqual(page.locator('.object-detection-box').count(),1,version)
                    if version=='v6':
                        self.assertTrue(page.locator('#findObjectStatus').inner_text().startswith('V6 experimental'))
                        page.locator('#findVersionDetails > summary').click()
                        self.assertTrue(page.locator('#findVersionSummary').is_visible())
                        self.assertIn('No accuracy improvement',page.locator('#findVersionSummary').inner_text())
                        page.locator('#findVersionDetails > summary').click()
                        self.assertFalse(page.locator('#findRunSettings').evaluate('e=>e.classList.contains("hidden")'))
                        self.assertEqual(json.loads(page.locator('#findRunConfigData').text_content())['minV3BoxCheckProbability'],.65)
                    if version=='v5':
                        evidence=json.loads(page.locator('#findEvidenceData').text_content())
                        self.assertEqual(evidence['evidenceVersion'],2)
                        self.assertGreater(len(evidence['acceptance']),0)
                        self.assertEqual(page.locator('.review-detection-box').count(),len(evidence['reviewBoxes']))
                # V6 edits are validated, recorded per run, and locked in flight.
                page.locator('#findVersionSelect').select_option('v6')
                self.assertTrue(page.locator('#findV6Settings').is_visible())
                page.locator('#findV6Settings').evaluate('(e)=>e.open=true')
                self.assertEqual(page.locator('#findV6-minDuplicatePairProbability').input_value(),'55')
                page.locator('#findV6-minV3BoxCheckProbability').fill('101')
                self.assertTrue(page.locator('#findObjectButton').is_disabled())
                page.locator('#findV6Settings > summary').click()
                self.assertFalse(page.locator('#findV6-minV3BoxCheckProbability').is_visible())
                self.assertTrue(page.locator('#findV6SettingsError').is_visible())
                page.locator('#findV6Settings > summary').click()
                page.locator('#findV6-minV3BoxCheckProbability').fill('')
                self.assertTrue(page.locator('#findObjectButton').is_disabled())
                page.locator('#findVersionSelect').select_option('v4')
                self.assertFalse(page.locator('#findV6Settings').is_visible())
                self.assertFalse(page.locator('#findV6SettingsError').is_visible())
                self.assertTrue(page.locator('#findObjectButton').is_enabled())
                page.locator('#findVersionSelect').select_option('v6')
                page.locator('#findV6SettingsReset').click()
                page.locator('#findV6-minV3BoxCheckProbability').fill('75.5')
                self.assertEqual(page.locator('#findV6SettingsState').inner_text(),'Custom')
                hold_next[0]=True
                page.locator('#findObjectButton').click()
                page.wait_for_function("document.querySelector('#findV6SettingsFields').disabled && document.querySelectorAll('.find-api-exchange').length > 0")
                self.assertTrue(page.locator('#findV6SettingsReset').is_disabled())
                self.assertTrue(page.locator('#findV6-minV3BoxCheckProbability').is_disabled())
                self.assertEqual(len(pending_api),1)
                # Native JSON popups preserve the page position and update in flight.
                exchange=page.locator('.find-api-exchange').first
                request_button=exchange.get_by_role('button',name='Request JSON',exact=True)
                response_button=exchange.get_by_role('button',name='Response JSON',exact=True)
                request_dialog=exchange.locator('dialog').nth(0)
                response_dialog=exchange.locator('dialog').nth(1)
                request_json=request_dialog.locator('pre')
                response_json=response_dialog.locator('pre')
                self.assertFalse(request_dialog.is_visible())
                self.assertFalse(response_dialog.is_visible())
                request_button.scroll_into_view_if_needed()
                page_before=page.evaluate('window.scrollY')
                request_button.click()
                self.assertTrue(request_dialog.is_visible())
                self.assertFalse(response_dialog.is_visible())
                self.assertEqual(json.loads(request_json.text_content())['request'],requests[-1][1])
                request_json.click(position={'x':15,'y':15})
                self.assertTrue(request_dialog.is_visible(),'Clicking inside must not dismiss the popup')
                request_dialog.get_by_role('button',name='Close').click()
                self.assertFalse(request_dialog.is_visible())
                self.assertTrue(request_button.evaluate('e=>document.activeElement===e'))
                self.assertAlmostEqual(page.evaluate('window.scrollY'),page_before,delta=1)
                response_button.press('Enter')
                self.assertTrue(response_dialog.is_visible())
                self.assertIn('Waiting for response',response_json.text_content())
                focused_close=response_dialog.get_by_role('button',name='Close').element_handle()
                route,payload=pending_api.pop()
                payload['diagnostic']={'longValue':'<b>'+('x'*2500),'items':list(range(60))}
                route.fulfill(json=payload)
                page.wait_for_function("!document.querySelector('#findObjectButton').disabled")
                self.assertTrue(response_dialog.is_visible())
                self.assertTrue(focused_close.evaluate('e=>e.isConnected && document.activeElement===e'))
                self.assertEqual(json.loads(response_json.text_content())['body'],payload)
                self.assertEqual(response_json.locator('b').count(),0)
                # The close button remains available while long JSON scrolls on desktop/mobile.
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':900})
                    dialog_body=response_dialog.locator('.find-api-json-dialog-body')
                    bounds=response_dialog.bounding_box()
                    self.assertGreaterEqual(bounds['x'],0)
                    self.assertLessEqual(bounds['x']+bounds['width'],width)
                    self.assertLessEqual(bounds['y']+bounds['height'],900)
                    self.assertTrue(response_json.evaluate('e=>e.scrollWidth<=e.clientWidth && e.scrollHeight===e.clientHeight'))
                    self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
                    page_before=page.evaluate('window.scrollY')
                    dialog_body.evaluate('e=>e.scrollTop=0')
                    bounds=dialog_body.bounding_box()
                    page.mouse.move(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
                    page.mouse.wheel(0,250)
                    page.wait_for_function("document.querySelector('dialog[open] .find-api-json-dialog-body').scrollTop>0")
                    self.assertAlmostEqual(page.evaluate('window.scrollY'),page_before,delta=1)
                    page.mouse.move(4,4)
                    page.mouse.wheel(0,250)
                    page.wait_for_timeout(100)
                    self.assertAlmostEqual(page.evaluate('window.scrollY'),page_before,delta=1)
                    close=response_dialog.get_by_role('button',name='Close')
                    close_bounds=close.bounding_box()
                    self.assertGreaterEqual(close_bounds['y'],0)
                    self.assertLessEqual(close_bounds['y']+close_bounds['height'],900)
                    close.focus()
                    page.keyboard.press('Tab')
                    self.assertTrue(dialog_body.evaluate('e=>document.activeElement===e'))
                    page.keyboard.press('Shift+Tab')
                    self.assertTrue(close.evaluate('e=>document.activeElement===e'))
                    response_button.evaluate('e=>e.focus()')
                    self.assertTrue(response_dialog.evaluate('e=>e.contains(document.activeElement)'))
                    # Dragging text out of the popup must not count as an outside click.
                    page.mouse.move(bounds['x']+20,bounds['y']+30)
                    page.mouse.down()
                    page.mouse.move(4,4)
                    page.mouse.up()
                    self.assertTrue(response_dialog.is_visible())
                page.keyboard.press('Escape')
                response_dialog.wait_for(state='hidden')
                self.assertTrue(response_button.evaluate('e=>document.activeElement===e'))
                self.assertAlmostEqual(page.evaluate('window.scrollY'),page_before,delta=1)
                response_button.click()
                self.assertEqual(response_dialog.locator('.find-api-json-dialog-body').evaluate('e=>e.scrollTop'),0)
                page.mouse.click(4,4)
                response_dialog.wait_for(state='hidden')
                self.assertTrue(response_button.evaluate('e=>document.activeElement===e'))
                page.set_viewport_size({'width':1440,'height':1100})
                config=json.loads(page.locator('#findRunConfigData').text_content())
                self.assertEqual(config['minV3BoxCheckProbability'],.755)
                self.assertIn('Custom',page.locator('#findRunSettingsSummary').inner_text())
                page.locator('#findV6SettingsReset').click()
                self.assertEqual(page.locator('#findV6SettingsState').inner_text(),'Defaults')
                self.assertEqual(json.loads(page.locator('#findRunConfigData').text_content()),config)
                page.locator('#findObjectButton').click()
                page.wait_for_function("!document.querySelector('#findObjectButton').disabled")
                self.assertEqual(page.locator('.find-api-json-dialog[open]').count(),0)
                self.assertEqual(json.loads(page.locator('#findRunConfigData').text_content())['minV3BoxCheckProbability'],.65)
                self.assertIn('Defaults',page.locator('#findRunSettingsSummary').inner_text())
                page.locator('#findNextPhoto').click()
                self.assertEqual(page.locator('#findPhotoSlider').input_value(),'1')
                self.assertEqual(page.locator('.find-api-exchange').count(),0)
                page.locator('[data-view="search"]').first.click()
                page.locator('#searchDatasetSelect').select_option(dataset['id'])
                page.locator('#semanticSearchQuery').fill('dogs')
                hold_next[0]=True
                page.locator('#imageSearchForm').evaluate('form=>form.requestSubmit()')
                page.wait_for_function("document.querySelector('#semanticSearchButton').disabled")
                self.assertTrue(page.locator('#searchDatasetSelect').is_disabled())
                self.assertTrue(page.locator('#searchPageSize').is_disabled())
                for _ in range(500):
                    if pending_api:break
                    page.wait_for_timeout(10)
                self.assertEqual(len(pending_api),1)
                route,payload=pending_api.pop();route.fulfill(json=payload)
                page.wait_for_function("!document.querySelector('#semanticSearchButton').disabled")
                self.assertEqual(page.locator('.semantic-result-card').count(),2)
                self.assertTrue(page.locator('#searchDatasetSelect').is_enabled())
                self.assertTrue(page.locator('#searchPageSize').is_enabled())
                hold_next[0]=True
                page.locator('#imageSearchForm').evaluate('form=>form.requestSubmit()')
                page.wait_for_function("document.querySelector('#semanticSearchButton').disabled")
                for _ in range(500):
                    if pending_api:break
                    page.wait_for_timeout(10)
                self.assertEqual(len(pending_api),1)
                route,payload=pending_api.pop();payload['answers'].pop('match_0');route.fulfill(json=payload)
                page.wait_for_function("!document.querySelector('#semanticSearchButton').disabled")
                self.assertIn('valid match probability',page.locator('.search-error').inner_text())
                self.assertEqual(page.locator('.semantic-result-card').count(),0)
                page.locator('[data-view="qa"]').first.click()
                page.wait_for_function("document.querySelector('#layoutDataset').options.length===2")
                self.assertEqual(page.locator('#layoutDataset').input_value(),'design2code')
                self.assertFalse(page.locator('#layoutOptionalChecks').evaluate('e=>e.open'))
                self.assertTrue(page.locator('#layoutPreviewEmpty').is_visible())
                self.assertFalse(page.locator('#layoutReferencePanel').is_visible())
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':1100})
                    self.assertGreaterEqual(page.locator('#layoutHtml').bounding_box()['height'],300)
                    self.assertGreaterEqual(page.locator('#layoutHtml').evaluate('e=>parseFloat(getComputedStyle(e).fontSize)'),13)
                    self.assertGreaterEqual(page.locator('#layoutRender').bounding_box()['height'],44)
                    self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
                page.set_viewport_size({'width':1440,'height':1100})
                page.locator('#layoutExample').select_option('001')
                page.wait_for_function("document.querySelector('#layoutHtml').value.includes('Module fixture') && !document.querySelector('#layoutValidate').disabled")
                self.assertTrue(page.locator('#layoutReferencePanel').is_visible())
                requests_before_preview=len(requests)
                page.locator('#layoutRender').click()
                page.wait_for_function("document.querySelector('#layoutStatus').textContent.startsWith('Preview ready')")
                self.assertEqual(len(requests),requests_before_preview,'Preview must not call the model')
                self.assertFalse(page.locator('#layoutPreviewEmpty').is_visible())
                self.assertTrue(page.locator('#layoutPreview').is_visible())
                self.assertTrue(page.locator('#layoutExport').is_disabled())
                # Optional requirements remain keyboard accessible and participate in validation.
                page.locator('#layoutOptionalChecks summary').focus()
                page.keyboard.press('Enter')
                page.locator('#layoutExpected').fill('a heading')
                self.assertTrue(page.locator('#layoutPreviewEmpty').is_visible())
                page.locator('#layoutValidate').click()
                page.wait_for_function("!document.querySelector('#layoutExport').disabled")
                self.assertIn('No issues flagged',page.locator('#layoutStatus').inner_text())
                self.assertEqual(page.locator('.layout-result').count(),5)
                self.assertTrue(all(tone=='ready' for tone in page.locator('.layout-result').evaluate_all('rows=>rows.map(e=>e.dataset.tone)')))
                self.assertIn('requirements',requests[-1][1]['questions'])
                page.locator('#layoutHtml').fill('<h1>Edited source</h1>')
                self.assertTrue(page.locator('#layoutExport').is_disabled())
                self.assertEqual(page.locator('.layout-result').count(),0)
                self.assertNotIn('No issues flagged',page.locator('#layoutStatus').inner_text())
                self.assertFalse(page.locator('#layoutPreview').is_visible())
                self.assertTrue(page.locator('#layoutReference').is_visible(),'Keep the reference when editing an example')
                # Malformed responses must show an error, with no successful report left behind.
                hold_next[0]=True
                page.locator('#layoutValidate').click()
                page.wait_for_function("document.querySelector('#layoutValidate').disabled")
                for _ in range(500):
                    if pending_api:break
                    page.wait_for_timeout(10)
                self.assertEqual(len(pending_api),1)
                route,payload=pending_api.pop();payload['answers'].pop('readability');route.fulfill(json=payload)
                page.wait_for_function("!document.querySelector('#layoutValidate').disabled")
                self.assertEqual(page.locator('#layoutStatus').get_attribute('data-tone'),'error')
                self.assertTrue(page.locator('#layoutExport').is_disabled())
                self.assertEqual(page.locator('.layout-result').count(),0)
                self.assertTrue(page.locator('#layoutPreview').is_visible(),'A validation error should keep the rendered preview')
                page.locator('#layoutViewport').select_option('mobile')
                self.assertEqual(page.locator('#layoutPreviewSize').inner_text(),'Mobile · 390 × 844')
                self.assertTrue(page.locator('#layoutPreviewEmpty').is_visible())
                self.assertEqual(page.locator('#layoutStatus').get_attribute('data-tone'),'neutral')
                page.locator('#layoutDataset').select_option('')
                self.assertFalse(page.locator('#layoutReferencePanel').is_visible())
                self.assertTrue(any(path=='/api/count-cars' for path,_ in requests))
                self.assertTrue(any('match_0' in body['questions'] for _,body in requests))
                self.assertTrue(any('overlap' in body['questions'] for _,body in requests))
                # New benchmark snapshots must execute all strategy dependencies, not app initialization.
                with tempfile.TemporaryDirectory() as directory:
                    out=Path(directory)
                    hashes=freeze_modules(out,'tools/find/engine.js')
                    source=benchmark_source(out,{'moduleHashes':hashes})
                    page.route('**/find-eval/runner',lambda route:route.fulfill(content_type='text/html',body='<script type="module" src="/find-eval/app.js"></script>'))
                    page.route('**/find-eval/app.js',lambda route:route.fulfill(content_type='text/javascript',body=source))
                    page.route('**/find-eval/modules/**',lambda route:route.fulfill(content_type='text/javascript',body=(out/'modules'/route.request.url.split('/find-eval/modules/',1)[1]).read_bytes()))
                    page.goto('http://jev-tools.test/find-eval/runner')
                    page.wait_for_function('typeof window.runFindBenchmark === "function"')
                    for version in ['v1','v2','v3','v4','v5','v6']:
                        result=page.evaluate('args=>window.runFindBenchmark(args)',{'url':'/fixture.png','id':'fixture','target':'dogs','version':version,'config':{'minV3BoxCheckProbability':.8} if version=='v6' else {}})
                        self.assertIsNone(result['error'],result['error'])
                        if version=='v6':self.assertEqual(result['result']['config']['minV3BoxCheckProbability'],.8)
                        self.assertEqual(len(result['result']['boxes']),1)
                        self.assertEqual(len(result['attempts']),result['result']['apiRequests'])
                        self.assertTrue(all(attempt['ok'] for attempt in result['attempts']))
                self.assertFalse(errors,errors)
                self.assertFalse(unexpected,unexpected)
            finally:
                browser.close()


    def test_original_crop_rounding_and_odd_padding_transforms(self):
        def serve(route):
            path=urlsplit(route.request.url).path
            if path=='/':route.fulfill(body='<html></html>',content_type='text/html');return
            route.fulfill(body=(ROOT/'web'/path.lstrip('/')).read_bytes(),content_type='text/javascript')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.route('**/*',serve);page.goto('http://jev-geometry.test/')
                data=page.evaluate("""async () => {
                  const {prepareImage}=await import('/image-assets.js');
                  const {cropImageRegion,mapCropBoxToPreparedImage}=await import('/tools/find/geometry.js');
                  const canvas=document.createElement('canvas');canvas.width=1200;canvas.height=123;
                  const blob=await new Promise(r=>canvas.toBlob(r,'image/png'));
                  const prepared=await prepareImage(blob,1568,true);
                  canvas.width=4001;canvas.height=2003;
                  const input={left:.1234,top:.2345,right:.5345,bottom:.7891};
                  const crop=await cropImageRegion(canvas,input);
                  const mapped=mapCropBoxToPreparedImage(crop.content,crop);
                  return {content:prepared.content,sourceRetained:prepared.sourceBlob===blob,
                    region:crop.region,mapped,width:crop.width,height:crop.height};
                }""")
                self.assertAlmostEqual(data['content']['top'],59/280)
                self.assertAlmostEqual(data['content']['bottom'],220/280)
                self.assertTrue(data['sourceRetained'])
                self.assertAlmostEqual(data['region']['left'],493/4001)
                self.assertAlmostEqual(data['region']['right'],2139/4001)
                self.assertEqual(data['mapped'],data['region'])
                self.assertLessEqual(max(data['width'],data['height']),1568)
            finally:browser.close()
