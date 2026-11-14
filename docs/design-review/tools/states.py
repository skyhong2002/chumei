"""Screenshot inventory for the design review.

docs/design-review/states.md documents the same IDs; change both together and
only between rounds that re-shoot the baseline.

data:    normal | empty | error | loading  (intercepts /data/*.json and /api/status.json)
session: out | in        theme: default (the site's dark default) | light (chosen in 外觀)   click: selectors clicked in order after load
type:    text typed after the clicks       anchor: start the shot here
viewport_only: capture only the first screen
"""

SIZES = {
    'desktop': {'width': 1440, 'height': 900, 'scale': 1, 'max_height': 2700, 'mobile': False},
    'mobile': {'width': 390, 'height': 844, 'scale': 2, 'max_height': 1688, 'mobile': True},
}

EVENT_RICH = '/event/evt_nyculife_qy2s4vs6j8p5/'
EVENT_SPARSE = '/event/evt_9f1b235dfb82/'
ORG_RICH = '/org/47/'
ORG_EMPTY = '/org/306/'


def s(id, path, **options):
    return {'id': id, 'path': path, **options}


STATES = [
    # Home: post river
    s('home', '/'),
    s('home-light', '/', theme='light'),
    s('home-loading', '/', data='loading'),
    s('home-error', '/', data='error'),
    s('home-empty', '/', data='empty'),
    s('home-events-only', '/?kind=events'),
    s('home-search-open', '/', click=['.topbar-search:visible, .nav-search:visible'], type='演講', viewport_only=True),
    s('home-signed-in', '/', session='in', click=['.nav-more > summary'], viewport_only=True),
    # Events
    s('events', '/events/'),
    s('events-light', '/events/', theme='light'),
    s('events-filtered', '/events/?school=nycu&cat=%E6%BC%94%E8%AC%9B'),
    s('events-no-results', '/events/?q=zzqxv'),
    s('events-loading', '/events/', data='loading'),
    s('events-error', '/events/', data='error'),
    s('events-empty', '/events/', data='empty'),
    # Calendar and stories (stories: frame only, mock media)
    s('calendar', '/calendar/'),
    s('calendar-filtered', '/calendar/?school=nthu&cat=%E8%97%9D%E6%96%87'),
    s('calendar-loading', '/calendar/', data='loading'),
    s('stories', '/stories/'),
    s('stories-empty', '/stories/', data='empty'),
    # Subscribe, notify, status, about
    s('subscribe', '/subscribe/'),
    s('subscribe-signed-in', '/subscribe/', session='in'),
    s('notify', '/notify/'),
    s('notify-signed-in', '/notify/', session='in'),
    s('status', '/status/'),
    s('status-error', '/status/', data='error'),
    s('about', '/about/'),
    # Event and organization pages
    s('event-rich', EVENT_RICH),
    s('event-rich-light', EVENT_RICH, theme='light'),
    s('event-sparse', EVENT_SPARSE),
    s('event-signed-in', EVENT_RICH, session='in'),
    s('org-rich', ORG_RICH),
    s('org-empty', ORG_EMPTY),
    # Directory
    s('source', '/source/'),
    s('source-light', '/source/', theme='light'),
    s('source-search', '/source/?q=%E5%90%89%E4%BB%96'),
    s('source-followed-empty', '/source/?follow=on'),
    s('source-error', '/source/', data='error'),
    # Account and submit
    s('submit', '/submit/'),
    s('submit-signed-in', '/submit/', session='in'),
    s('account', '/account/'),
    s('account-signed-in', '/account/', session='in'),
    s('account-signed-in-light', '/account/', session='in', theme='light'),
    s('not-found', '/no-such-page/'),
]

# Reference sites: photographed once and reused in every round.
REFERENCES = [
    {'id': 'accupass-home', 'url': 'https://www.accupass.com/', 'locale': 'zh-TW'},
    {'id': 'accupass-search', 'url': 'https://www.accupass.com/search?q=%E8%AC%9B%E5%BA%A7', 'locale': 'zh-TW'},
    {'id': 'luma-taipei', 'url': 'https://luma.com/taipei', 'locale': 'zh-TW'},
    {'id': 'luma-discover', 'url': 'https://luma.com/discover', 'locale': 'zh-TW'},
    {'id': 'nycu-life-events', 'url': 'https://events.life.nycu.edu.tw/', 'locale': 'zh-TW'},
]

# Fixed clock: the snapshot's evaluation time, so relative times never drift.
NOW = '2026-11-12T15:30:00+08:00'
