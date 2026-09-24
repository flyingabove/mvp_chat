"""Real browser regression flow for the mobile/PWA repair (Chromium and WebKit)."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8899/')
    parser.add_argument('--output', required=True)
    parser.add_argument('--expected-api-host', help='Require every API request to use this host')
    parser.add_argument('--mode', choices=('all', 'desktop', 'iphone', 'standalone'), default='all')
    parser.add_argument('--mock-chat-reply', action='store_true',
                        help='Exercise UI with a deterministic reply if the external story model is unavailable')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        modes = ('desktop', 'iphone', 'standalone') if args.mode == 'all' else (args.mode,)
        for mode in modes:
            browser = (p.chromium if mode == 'desktop' else p.webkit).launch()
            device = {'viewport': {'width': 1440, 'height': 1000}} if mode == 'desktop' else dict(p.devices['iPhone 14'])
            if mode != 'desktop':
                device['viewport'] = {'width': 390, 'height': 844 if mode == 'standalone' else 664}
                device['screen'] = {'width': 390, 'height': 844}
            context = browser.new_context(**device, service_workers='block' if args.mock_chat_reply else 'allow')
            context.add_init_script("localStorage.setItem('storieschat_ios_install_dismissed','1');")
            if mode == 'standalone':
                context.add_init_script("""Object.defineProperty(navigator, 'standalone', {value:true});
                  document.addEventListener('DOMContentLoaded', () => {
                    document.documentElement.style.setProperty('--safe-top','47px');
                    document.documentElement.style.setProperty('--safe-bottom','34px');
                  });""")
            page = context.new_page()
            errors, hosts, failed_api, http_api_errors = [], set(), [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda message: errors.append('console: ' + message.text) if message.type == 'error' else None)
            page.on('request', lambda r: hosts.add(urlsplit(r.url).netloc) if '/api/' in urlsplit(r.url).path else None)
            page.on('requestfailed', lambda r: failed_api.append(urlsplit(r.url).path) if '/api/' in urlsplit(r.url).path else None)
            page.on('response', lambda r: http_api_errors.append({'path': urlsplit(r.url).path, 'status': r.status}) if '/api/' in urlsplit(r.url).path and r.status >= 400 else None)
            try:
                page.goto(args.url, wait_until='networkidle')
                page.locator('#home-guest-pill').click()
                page.locator('.game-card').filter(has_text='Terrace in the City').first.click()
                page.locator('#modal-play-btn').click()
                page.locator('#onboard-continue-btn').click()
                opener = page.locator('#chat-messages .msg-bubble.npc').first
                opener.wait_for(timeout=120000)
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
                assert 400 < len(opener.inner_text()) < 1400
                assert opener.locator('.scene-speech').count() == 2
                assert opener.locator('.scene-narration').count() >= 3
                assert len(set(opener.locator('.speaker-name').all_inner_texts())) == 2
                opener.evaluate("e=>e.scrollIntoView({block:'start'})")
                page.screenshot(path=str(output / f'{mode}-opening.png'))
                assert page.locator('#chat-image-btn').count() == 0
                assert page.locator('#chat-avatar img').get_attribute('src').endswith('six_strangers_house.jpg')
                assert page.locator('.atlas-host').count() == 0
                inline = page.get_by_role('button', name='Open world map full screen')
                inline.click()
                assert page.locator('#map-modal').evaluate('(e)=>e.classList.contains("fullscreen")')
                assert page.locator('.atlas-host').count() == 0
                close_box = page.locator('#map-modal-close').bounding_box()
                assert close_box['width'] >= 56 and close_box['y'] >= (47 if mode == 'standalone' else 0)
                assert page.locator('#map-modal-img').evaluate('(e)=>e.naturalWidth') >= 1536
                page.locator('#map-modal-img').evaluate("""e=>{
                  const touch=(type, points)=>{const ev=new Event(type,{bubbles:true,cancelable:true});
                    Object.defineProperty(ev,'touches',{value:points.map(([clientX,clientY])=>({clientX,clientY}))});e.dispatchEvent(ev)};
                  touch('touchstart',[[120,300],[220,300]]);
                  touch('touchmove',[[90,300],[250,300]]);
                  touch('touchend',[]);
                }""")
                assert 'scale(1.6)' in page.locator('#map-modal-img').get_attribute('style')
                page.locator('#map-modal-img').evaluate("""e=>{
                  const touch=(type, points)=>{const ev=new Event(type,{bubbles:true,cancelable:true});
                    Object.defineProperty(ev,'touches',{value:points.map(([clientX,clientY])=>({clientX,clientY}))});e.dispatchEvent(ev)};
                  touch('touchstart',[[90,300],[250,300]]);
                  touch('touchmove',[[120,300],[220,300]]);
                  touch('touchend',[]);
                }""")
                assert 'scale(1)' in page.locator('#map-modal-img').get_attribute('style')
                page.screenshot(path=str(output / f'{mode}-map.png'))
                page.locator('#map-modal-close').click()
                page.locator('#chat-text-input').fill('[MAP]')
                page.locator('#chat-send-btn').click()
                page.locator('.atlas-host').wait_for()
                page.locator('.atlas-place').filter(has_text='Living Room').first.click()
                assert 'Relax on the sofas' in page.locator('.atlas-detail').inner_text()
                assert 'scene_derived' not in page.locator('.atlas-host').inner_text()
                page.locator('#map-modal-close').click()
                if args.mock_chat_reply:
                    scripted = {
                        'reply': 'Two housemates greet you.\n\nMizuki Shida: Welcome home!\n\nMakoto Hasegawa: Hey, good to meet you.',
                        'segments': [
                            {'kind': 'narration', 'text': 'Two housemates greet you.'},
                            {'kind': 'dialogue', 'speaker_id': 'mizuki', 'speaker_name': 'Mizuki Shida',
                             'portrait_url': '/img/characters/Mizuki_Shida.png', 'text': 'Welcome home!'},
                            {'kind': 'dialogue', 'speaker_id': 'makoto', 'speaker_name': 'Makoto Hasegawa',
                             'portrait_url': '/img/characters/Makoto_Hasegawa.png', 'text': 'Hey, good to meet you.'},
                        ],
                        'character': 'default', 'usage': {'total_tokens': 0},
                    }
                    page.route('**/api/chat', lambda route: route.fulfill(
                        status=200, content_type='application/json',
                        body=json.dumps(scripted, ensure_ascii=False)))
                page.locator('#chat-text-input').fill('I introduce myself and ask two housemates to tell me their names and say hello.')
                prior = page.locator('#chat-messages .msg-bubble.npc').count()
                with page.expect_response(lambda r: '/api/chat' in r.url, timeout=180000) as chat_response:
                    page.locator('#chat-send-btn').click()
                response = chat_response.value
                payload = response.json()
                (output / f'{mode}-reply.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
                assert response.ok and payload.get('reply'), {'status': response.status, 'payload': payload}
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
                page.wait_for_function('(n)=>document.querySelectorAll("#chat-messages .msg-bubble.npc").length>n', arg=prior, timeout=120000)
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
                assert page.locator('#chat-messages .msg-bubble.npc').last.locator('.scene-speech').count() >= 1
                portrait = page.locator('#chat-messages .msg-bubble.npc').last.locator('.scene-speech .speaker-portrait:has(img)').first
                assert portrait.bounding_box()['width'] >= 68
                portrait.click()
                assert page.locator('#portrait-viewer').evaluate('(e)=>e.open')
                assert page.locator('#portrait-viewer .portrait-full img').count() == 1
                page.wait_for_function("document.querySelector('#portrait-viewer .portrait-full img').naturalWidth >= 1254")
                assert portrait.locator('img').evaluate('(e)=>e.naturalWidth') >= 288
                page.screenshot(path=str(output / f'{mode}-portrait.png'))
                page.locator('#portrait-viewer .portrait-close').click()
                page.locator('#chat-messages').evaluate('(e)=>e.scrollTop=e.scrollHeight')
                page.screenshot(path=str(output / f'{mode}-chat.png'))
                nav = page.locator('#tab-update-app').evaluate('(e)=>e.parentElement.getBoundingClientRect().bottom')
                height = page.evaluate('screen.height' if mode == 'standalone' else 'innerHeight')
                assert abs(nav - height) < 2, (nav, height)
                if mode == 'standalone':
                    page.locator('#chat-text-input').focus()
                    page.evaluate("""() => {
                      Object.defineProperty(visualViewport,'height',{configurable:true,get:()=>500});
                      visualViewport.dispatchEvent(new Event('resize'));
                    }""")
                    page.wait_for_function("document.documentElement.classList.contains('keyboard-open')")
                    assert not page.locator('#tab-bar').is_visible()
                    composer_bottom = page.locator('#chat-input-area').bounding_box()['y'] + page.locator('#chat-input-area').bounding_box()['height']
                    assert composer_bottom <= 510, composer_bottom
                    page.screenshot(path=str(output / 'standalone-keyboard-simulated.png'))
                    page.evaluate("""() => {
                      delete visualViewport.height;
                      document.querySelector('#chat-text-input').blur();
                      visualViewport.dispatchEvent(new Event('resize'));
                    }""")
                    page.wait_for_function("!document.documentElement.classList.contains('keyboard-open')")
                page.locator('#chat-back-btn').click()
                content = page.locator('.item-content').first
                box = content.bounding_box()
                assert box['width'] <= page.evaluate('innerWidth')
                # Tap the far-right end: must resume, not enter the swipe state.
                content.click(position={'x': box['width'] - 15, 'y': box['height'] / 2})
                page.locator('#chat-text-input').wait_for(state='visible')
                page.locator('#chat-back-btn').click()
                content = page.locator('.item-content').first
                content.evaluate("""e=>{for(const [type,x] of [['touchstart',300],['touchmove',205],['touchend',205]]) { const event=new Event(type,{bubbles:true});Object.defineProperty(event,'touches',{value:type==='touchend'?[]:[{clientX:x,clientY:180}]});e.dispatchEvent(event);}}""")
                delete = page.locator('.game-list-item.swiped .delete-bg').first
                assert delete.inner_text() == '×'
                page.wait_for_timeout(400)  # Let the screen and swipe transitions finish for visual QA.
                page.screenshot(path=str(output / f'{mode}-games.png'))
                delete.click()
                assert page.locator('#confirm-title').inner_text() == 'Delete Game?'
                page.locator('#confirm-cancel').click()
                # Clear a deliberately seeded stale cache using the real bottom action.
                page.evaluate("async()=>{const c=await caches.open('storieschat-old-test');await c.put('/stale-test',new Response('old'));}")
                page.evaluate("localStorage.setItem('storieschat-reset-test','stale')")
                page.locator('#tab-update-app').click()
                page.wait_for_url('**_hr=*', timeout=30000)
                page.wait_for_load_state('networkidle')
                assert 'storieschat-old-test' not in page.evaluate('async()=>await caches.keys()')
                assert page.evaluate("localStorage.getItem('storieschat-reset-test')") is None
                assert not errors, errors
                assert not failed_api, failed_api
                assert not http_api_errors, http_api_errors
                if args.expected_api_host:
                    assert hosts == {args.expected_api_host}, hosts
                print(json.dumps({'mode':mode,'result':'passed','api_hosts':sorted(hosts),
                    'mock_chat_reply':args.mock_chat_reply,
                    'page_or_console_errors':errors,'failed_api_requests':failed_api,
                    'http_api_errors':http_api_errors}), flush=True)
            except Exception:
                page.screenshot(path=str(output / f'{mode}-failure.png'))
                print(json.dumps({'mode':mode,'errors':errors,'url':page.url}), flush=True)
                raise
            finally:
                context.close()
                browser.close()

if __name__ == '__main__':
    main()
