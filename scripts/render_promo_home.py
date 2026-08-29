"""Render the curated 390x844 home screenshot used by make_promo.py.

The promo fixture intentionally keeps a stable launch-day story row and two real
feed posts so later site updates do not silently change the marketing artwork.
"""

import base64
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from chumei_lib import ROOT


SITE = ROOT / "site"
PROMO = ROOT / "state" / "promo"
OUTPUT = PROMO / "shot-home.png"


def data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


class QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def log_message(self, _format, *args):
        pass


def find_post_html(page, query, predicate):
    origin = page.evaluate("location.origin")
    page.goto(f"{origin}/?q={quote(query)}", wait_until="networkidle")
    page.wait_for_selector(".feed-post")
    result = page.evaluate(
        """predicate => {
          const posts = [...document.querySelectorAll('.feed-post')];
          const hit = posts.find(post => {
            const name = post.querySelector('.feed-name')?.textContent.trim() || '';
            const text = post.querySelector('.feed-text')?.textContent.trim() || '';
            return predicate.name === name && text.startsWith(predicate.textStart) &&
              (!predicate.textExclude || !text.includes(predicate.textExclude));
          });
          return hit ? hit.outerHTML : null;
        }""",
        predicate,
    )
    if not result:
        raise RuntimeError(f"promo post not found: {predicate}")
    return result


def render():
    stories = [
        ("nycu_harmonica", "竹韻口琴社", "nycu", data_url(PROMO / "bamboo-story-2026-08-09.png")),
        ("nthu_rainbowclub", "彩虹同志社", "nthu", "/assets/stories/3973509950880433200.jpg"),
        ("nycu.life", "NYCU LIFE", "nycu", "/assets/stories/3973704510035077217.jpg"),
        ("nycu_artscenter", "藝文中心", "nycu", data_url(PROMO / "artscenter-story-114-2.png")),
        ("nthu_sa", "清大學生會", "nthu", "/assets/stories/3973418094782906873.jpg"),
    ]

    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 390, "height": 844},
                device_scale_factor=3,
                color_scheme="dark",
                locale="zh-TW",
            )
            page.goto(base_url + "/", wait_until="networkidle")
            page.evaluate("document.fonts.ready")

            library_html = find_post_html(
                page,
                "OpenHouse",
                {"name": "清大圖書館", "textStart": "📢各位清華新生們看過來！", "textExclude": ""},
            )
            yangming_html = find_post_html(
                page,
                "2026社團博覽會",
                {
                    "name": "陽明學生會（陽明交大學生會陽明分會）",
                    "textStart": "【2026社團博覽會】",
                    "textExclude": "資訊更新",
                },
            )

            page.evaluate(
                r"""([stories, yangmingHtml, libraryHtml]) => {
                  const esc = s => String(s).replace(/[&<>\"]/g, c => (
                    {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]
                  ));
                  const style = document.createElement('style');
                  style.textContent = `
                    #story-strip.promo-five { display:grid !important; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; overflow:hidden; padding:10px 5px 14px; }
                    #story-strip.promo-five .story-item { width:64px; min-width:0; }
                    #story-strip.promo-five .story-ring { width:58px; height:58px; }
                    #story-strip.promo-five .story-name { font-size:.68rem; overflow:visible; text-overflow:clip; }
                    #post-feed .feed-cols { display:block !important; width:100% !important; overflow:visible !important; }
                    #post-feed .feed-col { width:100% !important; max-width:none !important; min-width:0 !important; }
                  `;
                  document.head.appendChild(style);

                  const strip = document.getElementById('story-strip');
                  strip.hidden = false;
                  strip.classList.add('promo-five');
                  strip.innerHTML = stories.map(([user, name, school, media]) =>
                    `<button class="story-item" data-user="${esc(user)}" aria-label="${esc(name)} 的限時動態">` +
                    `<span class="story-ring ring-${esc(school)}"><img src="${esc(media)}" alt=""></span>` +
                    `<span class="story-name">${esc(name)}</span></button>`
                  ).join('');

                  const fromHtml = html => {
                    const template = document.createElement('template');
                    template.innerHTML = html.trim();
                    return template.content.firstElementChild;
                  };
                  const compact = (post, name, text, age) => {
                    post.querySelector('.feed-name a, .feed-name').textContent = name;
                    post.querySelector('.feed-time').textContent = age;
                    post.querySelectorAll('[data-org-name]').forEach(el => el.dataset.orgName = name);
                    const body = post.querySelector('.feed-text');
                    body.classList.remove('is-long');
                    body.textContent = text;
                    post.querySelector('.feed-text-toggle')?.remove();
                    post.querySelector('.feed-evs')?.remove();
                    return post;
                  };
                  const yangming = compact(
                    fromHtml(yangmingHtml),
                    '陽明學生會',
                    '【2026 社團博覽會】\n8/31（一）11:00–17:00｜陽明校區活動中心\n廣場',
                    '4 天前'
                  );
                  const library = compact(
                    fromHtml(libraryHtml),
                    '清大圖書館',
                    '【新生座談會 Open House】\n8/30（日）10:00–18:00｜清大總圖書館',
                    '2 天前'
                  );

                  const feed = document.getElementById('post-feed');
                  feed.innerHTML = '<div class="feed-cols"><section class="feed-col"><div class="col-body"></div></section></div>';
                  const column = feed.querySelector('.col-body');
                  column.append(yangming, library);
                  document.querySelector('.feed-filters')?.classList.remove('fon');
                  history.replaceState(null, '', '/');
                  window.scrollTo(0, 0);
                }""",
                [stories, yangming_html, library_html],
            )
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(700)
            page.wait_for_function("[...document.images].every(image => image.complete)")
            page.screenshot(path=str(OUTPUT))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print(f"ok → {OUTPUT}")


if __name__ == "__main__":
    render()
