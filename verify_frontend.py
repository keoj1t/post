"""End-to-end checks use a temporary account database and their own server."""
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import closing
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8081'
with tempfile.TemporaryDirectory(prefix='jana-check-') as temp:
    db_path = Path(temp) / 'accounts.sqlite3'
    env = {**os.environ, 'JANA_AUTH_DB': str(db_path)}
    server = subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8081'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(URL+'/health',timeout=1)
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Test server did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            context=browser.new_context(accept_downloads=True)
            page=context.new_page()
            failures,external=[],[]
            page.on('pageerror',lambda error:failures.append(str(error)))
            page.on('request',lambda request:external.append(request.url) if not request.url.startswith(URL) else None)
            page.goto(URL)
            assert page.locator('[data-tab=about]').count()==0
            assert page.locator('[data-tab=errors]').count()==1
            assert page.evaluate("getComputedStyle(document.body).backgroundColor")=='rgb(250, 251, 252)'
            assert page.locator('.input-panel').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)'
            assert page.locator('#openLogin').is_visible()
            for forbidden in ['FastAPI','SQLite','Swagger','Terricon','CHALLENGE','/parse/batch','КАТО']:
                assert forbidden not in page.locator('body').inner_text()
            # Registration, actual session cookie, and persistence after reload.
            page.click('#openRegister')
            page.fill('#authName','Тест Пайдаланушы')
            page.fill('#authEmail','browser-check@example.test')
            page.fill('#authPassword','Test-password-2026!')
            page.click('#authSubmit')
            page.wait_for_selector('#account:visible')
            cookie=next(c for c in context.cookies() if c['name']=='jana_session')
            assert cookie['httpOnly'] and cookie['sameSite']=='Strict'
            assert page.request.get(URL+'/auth/me').json()['user']['email']=='browser-check@example.test'
            page.reload()
            page.wait_for_selector('#account:visible')
            assert 'Тест' in page.locator('#accountName').inner_text()
            # Logout invalidates the session on the server.
            old_cookie=cookie['value']
            page.click('#logout')
            page.wait_for_selector('#openLogin:visible')
            invalidated=page.request.get(URL+'/auth/me',headers={'Cookie':'jana_session='+old_cookie}).json()
            assert invalidated['user'] is None
            # Wrong password and duplicate email do not succeed.
            page.click('#openLogin')
            page.fill('#authEmail','browser-check@example.test')
            page.fill('#authPassword','Wrong-password-2026!')
            page.click('#authSubmit')
            page.wait_for_function("document.querySelector('#authError').textContent.includes('Неверная')")
            page.fill('#authPassword','Test-password-2026!')
            page.click('#authSubmit')
            page.wait_for_selector('#account:visible')
            duplicate=page.request.post(URL+'/auth/register',data={'name':'Другой','email':'browser-check@example.test','password':'Test-password-2026!'})
            assert duplicate.status==409
            short=page.request.post(URL+'/auth/register',data={'name':'Тест','email':'short@example.test','password':'short'})
            assert short.status==422
            cross=page.request.post(URL+'/auth/logout',data={},headers={'Origin':'https://other.example'})
            assert cross.status==403
            with closing(sqlite3.connect(db_path)) as db:
                user=db.execute('SELECT salt,password_hash FROM users').fetchone()
                assert len(user[0])==32 and len(user[1])==64
                assert 'Test-password' not in user[1]
                tokens=[r[0] for r in db.execute('SELECT token_hash FROM sessions')]
                assert old_cookie not in tokens
            # Existing address functionality remains intact.
            page.click('#example')
            with page.expect_response('**/parse/batch') as response:
                page.click('#run')
            assert response.value.status==200
            page.wait_for_function("document.querySelector('#tbody').children.length===5")
            assert page.locator('#tbody tr').first.locator('mark').count()>=3
            raw=page.evaluate('JSON.stringify(rows)')
            page.select_option('#language','kk')
            assert page.locator('html').get_attribute('lang')=='kk'
            assert page.locator('#run').inner_text()=='Мекенжайларды өңдеу →'
            assert page.locator('#thead').inner_text().find('Бастапқы мекенжай')>=0
            assert page.evaluate('JSON.stringify(rows)')==raw
            page.reload()
            assert page.locator('html').get_attribute('lang')=='kk'
            page.select_option('#language','ru')
            page.click('#example');page.click('#run')
            page.wait_for_function("document.querySelector('#tbody').children.length===5")
            house=page.locator('#tbody tr').first.locator('td.f').nth(6)
            original_house=house.inner_text()
            house.fill('999');house.press('Tab')
            assert page.locator('#tbody tr').first.locator('.edited').count()==1
            with page.expect_download() as pending:
                page.click('#dlJson')
            data=json.loads(Path(pending.value.path()).read_text(encoding='utf-8'))
            assert data[0]['house']=='999' and 'reviewed' not in data[0]
            page.click('#undo')
            assert page.locator('#tbody tr').first.locator('td.f').nth(6).inner_text()==original_house
            page.click('[data-tab=tokens]')
            assert page.locator('#tokenDetail mark').count()>=3
            page.click('[data-tab=queue]');page.check('#queueAll');page.click('#confirm')
            assert '1 из 5' in page.locator('#progressText').inner_text()
            page.click('[data-tab=parse]');page.check('#exportReviewed')
            with page.expect_download() as pending:
                page.click('#dlCsv')
            csv=Path(pending.value.path()).read_bytes()
            assert csv.startswith(b'\xef\xbb\xbf') and b'reviewed' in csv
            page.fill('#search','no-match-123')
            assert 'Совпадений' in page.locator('#tbody').inner_text()
            page.fill('#search','')
            page.set_input_files('#file',{'name':'addresses.txt','mimeType':'text/plain','buffer':'Абая 5'.encode()})
            page.wait_for_function("document.querySelector('#input').value==='Абая 5'")
            assert page.evaluate("buildPayload('  Абая 5  ')[0].raw_address")=='  Абая 5  '
            # New parser variants are also highlighted in the original spelling.
            page.fill('#input','жм Коктал1 преулок xxx дм1')
            page.click('#run')
            page.wait_for_function("document.querySelector('#total').textContent==='1'")
            residential=page.locator('#tbody tr').first
            assert residential.locator('td.f').nth(3).inner_text()=='Коктал 1'
            assert residential.locator('td.f').nth(4).inner_text()=='переулок'
            assert residential.locator('td.f').nth(5).inner_text()=='xxx'
            assert residential.locator('td.f').nth(6).inner_text()=='1'
            assert residential.locator('mark[title="Жилмассив"]').inner_text()=='жм Коктал1'
            assert residential.locator('mark[title="Тип улицы"]').inner_text()=='преулок'
            assert residential.locator('mark[title="Дом"]').inner_text()=='дм1'
            assert residential.locator('td.raw').inner_text()=='жм Коктал1 преулок xxx дм1'
            page.select_option('#language','kk')
            assert page.locator('.hero-steps').inner_text()=='Қосыңыз\nТексеріңіз\nСақтаңыз'
            page.select_option('#language','ru')
            # Token demonstration, editable details, queue exports and error examples.
            page.click('[data-tab=tokens]')
            page.click('#tokenDemo')
            page.wait_for_function("document.querySelector('#tokenDetail input[data-field=apartment]').value==='69'")
            assert page.locator('#tokenDetail mark[title="Квартал"]').inner_text()=='66'
            assert page.locator('#tokenDetail mark[title="Дом"]').inner_text()=='12дом'
            assert page.locator('#tokenDetail mark[title="Кв."]').inner_text()=='69квартира'
            detail_house=page.locator('#tokenDetail input[data-field=house]')
            detail_house.fill('22')
            assert page.locator('#tokenDetail .edited').count()==1
            page.click('[data-tab=parse]')
            assert page.locator('#tbody tr').first.locator('td.f').nth(6).inner_text()=='22'
            page.click('[data-tab=tokens]');page.click('#tokenUndo')
            assert page.locator('#tokenDetail input[data-field=house]').input_value()=='12'
            full_example='жм пуси улица гарова астана алматинская область район сарыаркинский 3дом кварт4 подьедз5 эт4 под магазином алена'
            page.click('[data-tab=parse]');page.fill('#input',full_example);page.click('#run')
            page.wait_for_function("rows.length===1 && rows[0].floor==='4' && rows[0].city==='астана'")
            assert page.locator('#uncertain').inner_text()=='1'
            page.click('[data-tab=tokens]')
            assert 'не согласованы' in page.locator('#tokenDetail .record-checks').inner_text()
            page.click('[data-tab=queue]');page.uncheck('#queueAll')
            assert page.locator('#queueDetail input[data-field=entrance]').input_value()=='5'
            assert page.locator('#queueDetail input[data-field=floor]').input_value()=='4'
            page.locator('#queueDetail input[data-field=floor]').fill('7')
            page.click('#confirm')
            assert '1 из 1' in page.locator('#progressText').inner_text()
            page.check('#queueReviewed')
            with page.expect_download() as pending:
                page.click('#queueJson')
            queue_export=json.loads(Path(pending.value.path()).read_text(encoding='utf-8'))
            assert queue_export[0]['floor']=='7' and queue_export[0]['reviewed'] is True
            assert queue_export[0]['raw_address']==full_example
            page.click('[data-tab=errors]')
            assert page.locator('#errorsBody tr').count()==5
            assert page.locator('#title').inner_text()=='Ошибки и исправления'
            page.fill('#errorSearch','Коктал1')
            assert page.locator('#errorsBody tr').count()==1
            with page.expect_response('**/parse/batch'):
                page.locator('#errorsBody button').click()
            page.wait_for_function("rows.length===1 && rows[0].living_area==='Коктал 1'")
            page.click('[data-tab=errors]');page.fill('#errorSearch','')
            page.select_option('#language','kk')
            assert page.locator('#title').inner_text()=='Қателер мен түзетулер'
            assert 'Үтірсіз география' in page.locator('#errorsBody').inner_text()
            assert 'География без запятых' not in page.locator('#errorsBody').inner_text()
            page.select_option('#language','ru')
            # RU / KK, light / dark, all tabs and auth forms at required sizes.
            for width in [375,768,1440]:
                page.set_viewport_size({'width':width,'height':960})
                for lang in ['ru','kk']:
                    page.select_option('#language',lang)
                    for theme in ['light','dark']:
                        page.evaluate('(value)=>{theme=value;applyTheme()}',theme)
                        for tab in ['parse','tokens','queue','errors']:
                            page.click(f'[data-tab={tab}]')
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,lang,theme,tab)
                        page.click('[data-tab=parse]')
                        page.evaluate('window.scrollTo(0,0)')
                        page.evaluate("Promise.all(document.getAnimations().filter(a=>a.effect.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))")
                        page.screenshot(path=str(ROOT/f'.venv/preview-{width}-{lang}-{theme}.png'),full_page=True)
            page.evaluate("theme='light';applyTheme()")
            page.select_option('#language','kk')
            page.click('#logout');page.wait_for_selector('#openLogin:visible')
            page.click('#openRegister')
            assert page.locator('#authTitle').inner_text()=='Аккаунт ашу'
            page.screenshot(path=str(ROOT/'.venv/registration-kk.png'))
            page.click('#closeAuth')
            page.select_option('#language','ru')
            page.route('**/parse/batch',lambda route:route.fulfill(json=[{'id':i,'raw_address':f'Адрес {i}','house':'5','confidence':.5} for i in range(1200)]))
            page.fill('#input','Абая 5');page.click('#run')
            page.wait_for_function("document.querySelector('#total').textContent==='1200'")
            assert page.locator('#tbody tr').count()==50
            page.click('#next')
            assert '2 из 24' in page.locator('#page').inner_text()
            page.unroute('**/parse/batch')
            page.route('**/parse/batch',lambda route:route.fulfill(status=500,body='error'))
            page.click('#run');page.wait_for_selector('#retry:visible')
            assert 'временно недоступен' in page.locator('#status').inner_text()
            assert not failures,failures
            assert not external,external
            browser.close()
        print('PASS: auth, RU/KK, 48 layouts, token colors, editable details, queue corrections/export, error examples, geography warnings, parser, 1200 records, zero external requests.')
    finally:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            server.terminate()
        server.wait(timeout=10)
