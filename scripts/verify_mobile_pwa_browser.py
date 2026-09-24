"""Real browser regression flow for the mobile/PWA repair (Chromium and WebKit)."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8899/')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        for mode in ('desktop', 'iphone', 'standalone'):
            browser = (p.chromium if mode == 'desktop' else p.webkit).launch()
            context = browser.new_context(**({'viewport': {'width': 1440, 'height': 1000}} if mode == 'desktop' else p.devices['iPhone 13']))
            context.add_init_script("localStorage.setItem('storieschat_ios_install_dismissed','1');")
            if mode == 'standalone':
                context.add_init_script("Object.defineProperty(navigator, 'standalone', {value:true});")
            page = context.new_page()
            errors, hosts = [], set()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('request', lambda r: hosts.add(r.url.split('/')[2]) if '/api/' in r.url else None)
            try:
                page.goto(args.url, wait_until='networkidle')
                page.locator('#home-guest-pill').click()
                page.locator('.game-card').filter(has_text='Terrace in the City').first.click()
                page.locator('#modal-play-btn').click()
                page.locator('#onboard-continue-btn').click()
                opener = page.locator('#chat-messages .msg-bubble.npc').first
                opener.wait_for(timeout=120000)
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
                assert len(opener.inner_text()) < 260
                assert page.locator('#chat-image-btn').count() == 0
                assert page.locator('#chat-avatar img').get_attribute('src').endswith('six_strangers_house.jpg')
                assert page.locator('.atlas-host').count() == 0
                inline = page.get_by_role('button', name='Open world map full screen')
                inline.click()
                assert page.locator('#map-modal').evaluate('(e)=>e.classList.contains("fullscreen")')
                assert page.locator('.atlas-host').count() == 0
                page.locator('#map-modal-img').evaluate("""e=>{
                  const touch=(type, points)=>{const ev=new Event(type,{bubbles:true,cancelable:true});
                    Object.defineProperty(ev,'touches',{value:points.map(([clientX,clientY])=>({clientX,clientY}))});e.dispatchEvent(ev)};
                  touch('touchstart',[[120,300],[220,300]]);
                  touch('touchmove',[[90,300],[250,300]]);
                  touch('touchend',[]);
                }""")
                assert 'scale(1.6)' in page.locator('#map-modal-img').get_attribute('style')
                page.screenshot(path=str(output / f'{mode}-map.png'))
                page.locator('#map-modal-close').click()
                page.locator('#chat-text-input').fill('[MAP]')
                page.locator('#chat-send-btn').click()
                page.locator('.atlas-host').wait_for()
                page.locator('.atlas-place').filter(has_text='Living Room').first.click()
                assert 'Relax on the sofas' in page.locator('.atlas-detail').inner_text()
                assert 'scene_derived' not in page.locator('.atlas-host').inner_text()
                page.locator('#map-modal-close').click()
                page.locator('#chat-text-input').fill('I introduce myself and ask two housemates to tell me their names and say hello.')
                prior = page.locator('#chat-messages .msg-bubble.npc').count()
                with page.expect_response(lambda r: '/api/chat' in r.url, timeout=180000) as chat_response:
                    page.locator('#chat-send-btn').click()
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
                page.wait_for_function('(n)=>document.querySelectorAll("#chat-messages .msg-bubble.npc").length>n', arg=prior)
                page.wait_for_function("!document.querySelector('#chat-messages [aria-busy]')", timeout=120000)
                (output / f'{mode}-reply.json').write_text(json.dumps(chat_response.value.json(), ensure_ascii=False), encoding='utf-8')
                assert page.locator('#chat-messages .msg-bubble.npc').last.locator('.scene-speech').count() >= 1
                portrait = page.locator('#chat-messages .msg-bubble.npc').last.locator('.scene-speech .speaker-portrait:has(img)').first
                portrait.click()
                assert page.locator('#portrait-viewer').evaluate('(e)=>e.open')
                assert page.locator('#portrait-viewer .portrait-full img').count() == 1
                page.locator('#portrait-viewer .portrait-close').click()
                page.locator('#chat-messages').evaluate('(e)=>e.scrollTop=e.scrollHeight')
                page.screenshot(path=str(output / f'{mode}-chat.png'))
                nav = page.locator('#tab-update-app').evaluate('(e)=>e.parentElement.getBoundingClientRect().bottom')
                height = page.evaluate('innerHeight')
                assert abs(nav - height) < 2, (nav, height)
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
                print(json.dumps({'mode':mode,'result':'passed','api_hosts':sorted(hosts)}), flush=True)
            except Exception:
                page.screenshot(path=str(output / f'{mode}-failure.png'))
                print(json.dumps({'mode':mode,'errors':errors,'url':page.url}), flush=True)
                raise
            finally:
                context.close()
                browser.close()

if __name__ == '__main__':
    main()
