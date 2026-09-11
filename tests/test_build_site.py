import collections
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site


class AttachGeoTests(unittest.TestCase):
    def test_generic_gym_name_stays_on_known_campus(self):
        venues = build_site.load_venues()
        events = [
            {"campus": "nthu-main", "venue": "體育館2F（全）"},
            {"campus": "nycu-guangfu", "venue": "體育館2F（全）"},
        ]

        self.assertEqual(build_site.attach_geo(events, venues), 2)
        self.assertEqual(events[0]["campus"], "nthu-main")
        self.assertEqual(events[0]["geo"]["name"], "新體育館")
        self.assertEqual(events[1]["campus"], "nycu-guangfu")
        self.assertEqual(events[1]["geo"]["name"], "體育館")

    def test_all_registered_cross_campus_names_respect_the_known_campus(self):
        venues = build_site.load_venues()
        by_key = collections.defaultdict(list)
        for row in venues:
            for key in [row["name"], *row["aliases"]]:
                by_key[key].append(row)

        collisions = {
            key: rows for key, rows in by_key.items()
            if len({row["campus"] for row in rows}) > 1
        }
        self.assertIn("體育館", collisions)
        self.assertIn("工程一館", collisions)
        self.assertIn("學生活動中心", collisions)

        for key, rows in collisions.items():
            for row in rows:
                with self.subTest(venue=key, campus=row["campus"]):
                    event = {"campus": row["campus"], "venue": key}
                    build_site.attach_geo([event], venues)
                    self.assertEqual(event["campus"], row["campus"])
                    self.assertEqual(event["geo"]["name"], row["name"])

    def test_unregistered_name_cannot_jump_from_a_known_campus(self):
        event = {"campus": "nthu-main", "venue": "綜合球館"}

        build_site.attach_geo([event], build_site.load_venues())

        self.assertEqual(event["campus"], "nthu-main")
        self.assertTrue(event["geo"]["approximate"])
        self.assertEqual(
            (event["geo"]["lat"], event["geo"]["lng"]),
            build_site.CAMPUS_GEO["nthu-main"],
        )

    def test_unique_venue_can_fill_an_unknown_campus(self):
        event = {"campus": None, "venue": "旺宏館"}

        build_site.attach_geo([event], build_site.load_venues())

        self.assertEqual(event["campus"], "nthu-main")
        self.assertEqual(event["geo"]["name"], "總圖書館")


class OrgDisplayNameTests(unittest.TestCase):
    def test_school_and_campus_prefixes(self):
        self.assertEqual(build_site.org_display_name("口琴社", "nthu"), "清大口琴社")
        self.assertEqual(
            build_site.org_display_name("竹韻口琴社", "nycu", "guangfu"),
            "交大竹韻口琴社",
        )
        self.assertEqual(
            build_site.org_display_name("揚鳴口琴社", "nycu", "yangming"),
            "陽明揚鳴口琴社",
        )

    def test_offices_and_full_school_names_are_normalized(self):
        self.assertEqual(build_site.org_display_name("教務處", "nthu"), "清大教務處")
        self.assertEqual(
            build_site.org_display_name("國立陽明交通大學皮藝社", "nycu", "yangming"),
            "陽明皮藝社",
        )
        self.assertEqual(
            build_site.org_display_name("陽明交大圖書館", "nycu"),
            "陽明交大圖書館",
        )

    def test_joint_and_external_names(self):
        self.assertEqual(
            build_site.org_display_name("清大交大聯合柔道社", "both"),
            "清交聯合柔道社",
        )
        self.assertEqual(build_site.org_display_name("新竹市文化局", "external"), "新竹市文化局")


class StoryDisplayNameTests(unittest.TestCase):
    def test_school_prefixes_are_hidden(self):
        self.assertEqual(build_site.story_display_name("陽明交大竹韻口琴社"), "竹韻口琴社")
        self.assertEqual(build_site.story_display_name("清大教育心理與諮商學系"), "教育心理與諮商學系")
        self.assertEqual(build_site.story_display_name("國立清華大學學生會"), "學生會")
        self.assertEqual(build_site.story_display_name("交大電子競技社"), "電子競技社")

    def test_non_school_name_and_empty_fallback_are_preserved(self):
        self.assertEqual(build_site.story_display_name("陽明愛杏管弦樂團"), "陽明愛杏管弦樂團")
        self.assertEqual(build_site.story_display_name("國立清華大學"), "國立清華大學")


class PostCampusTests(unittest.TestCase):
    def test_directory_campus_wins_over_event_venue(self):
        self.assertEqual(
            build_site.post_campus(
                {"campus": "guangfu", "name": "交大竹韻口琴社"},
                [{"campus": "nycu-yangming"}],
            ),
            "guangfu",
        )

    def test_school_wide_source_uses_unambiguous_event_campus(self):
        self.assertEqual(
            build_site.post_campus(
                {"campus": None, "name": "陽明交大圖書館"},
                [{"campus": "nycu-yangming"}, {"campus": "online"}],
            ),
            "yangming",
        )

    def test_mixed_school_wide_source_stays_unassigned(self):
        self.assertIsNone(
            build_site.post_campus(
                {"campus": None, "name": "陽明交大圖書館"},
                [{"campus": "nycu-guangfu"}, {"campus": "nycu-yangming"}],
            )
        )

    def test_feed_label_uses_nycu_campus(self):
        self.assertEqual(
            build_site._feed_school_label({"school": "nycu", "campus": "guangfu"}),
            "交大",
        )
        self.assertEqual(
            build_site._feed_school_label({"school": "nycu", "campus": "yangming"}),
            "陽明",
        )
        self.assertEqual(build_site._feed_school_label({"school": "nthu"}), "清大")


class SourceTableTests(unittest.TestCase):
    def test_follow_is_the_default_sort_header(self):
        entry = {
            "id": 1,
            "name": "清大測試社",
            "school": "nthu",
            "campus": None,
            "kind": "club",
            "category": None,
            "links": [],
            "events": 0,
            "updated": None,
            "avatar": None,
        }

        rendered = build_site.source_table_html([entry])

        self.assertIn('class="src-th src-th-follow src-th-on" data-sort="follow">追蹤 ↓</button>', rendered)
        self.assertNotIn('data-sort="events">收錄 ↓</button>', rendered)


class FeedActionTests(unittest.TestCase):
    def test_event_chip_has_a_separate_accessible_going_action(self):
        rendered = build_site._feed_ev_chip({
            "id": "evt_test",
            "title": "測試活動",
            "start_at": "2026-09-01T19:00:00+08:00",
            "all_day": False,
        })

        self.assertIn('<div class="feed-ev-row">', rendered)
        self.assertIn('data-event-id="evt_test"', rendered)
        self.assertIn('aria-label="我會去：測試活動"', rendered)
        self.assertNotIn('<a class="feed-ev" data-id="evt_test" href="/event/evt_test/"><button', rendered)


class RelatedEventsTests(unittest.TestCase):
    @staticmethod
    def event(event_id, title, start_at, campus="nycu-guangfu", venue=None, category="市集", org_id=None):
        return {
            "id": event_id,
            "title": title,
            "start_at": start_at,
            "campus": campus,
            "venue": venue,
            "category": category,
            "org_id": org_id,
        }

    def test_social_expo_page_lists_other_booths_but_not_unrelated_same_time_event(self):
        parent = self.event(
            "parent", "2026 陽明交大社團博覽會", "2026-09-09T17:30:00+08:00", org_id=1)
        art = self.event(
            "art", "交大美術社｜9/9 圖書館前社博攤位", "2026-09-09T17:30:00+08:00",
            venue="圖書館前", org_id=2)
        dog = self.event(
            "dog", "汪汪社社團博覽會攤位", "2026-09-09T17:30:00+08:00",
            venue="工程三館前 40 號攤位", org_id=3)
        unrelated = self.event(
            "talk", "半導體職涯講座", "2026-09-09T17:30:00+08:00",
            venue="工程三館", category="演講", org_id=4)
        other_campus = self.event(
            "yangming", "陽明瑜珈社社團博覽會攤位", "2026-08-31T11:00:00+08:00",
            campus="nycu-yangming", org_id=5)

        related = build_site.related_events(parent, [parent, art, dog, unrelated, other_campus])

        self.assertEqual([event["id"] for event, _ in related], ["art", "dog"])
        self.assertTrue(all(reason == "同場社博" for _, reason in related))

    def test_same_organizer_is_left_to_existing_more_from_organizer_section(self):
        first = self.event("first", "Conversation Circle 秋季開幕場", "2026-09-22T12:00:00+08:00", org_id=8)
        second = self.event("second", "Conversation Circle 秋季第二場", "2026-10-13T12:00:00+08:00", org_id=8)

        self.assertEqual(build_site.related_events(first, [first, second]), [])

    def test_detail_page_renders_relation_reason_and_disclaimer(self):
        event = self.event("parent", "社團博覽會", "2026-09-09T17:30:00+08:00")
        event.update({
            "end_at": None, "all_day": False, "school": "nycu", "summary": "社團博覽會",
            "description": "", "organizer": "課外組", "organizer_type": "official", "reg": None,
            "price": None, "fee": None, "registration_url": None, "registration_deadline": None,
            "source": {"url": "https://example.com/post"}, "extraction": {"needs_review": False},
        })
        booth = self.event("booth", "美術社社博攤位", "2026-09-09T17:30:00+08:00")

        rendered = build_site.detail_page(event, related=[(booth, "同場社博")])

        self.assertIn("可能相關的活動", rendered)
        self.assertIn("實際關係以主辦單位公告為準", rendered)
        self.assertIn("美術社社博攤位", rendered)
        self.assertIn("同場社博", rendered)
        self.assertIn('data-event-title="社團博覽會"', rendered)
        self.assertIn('<span class="gb-go">我會去</span><span class="gb-going">已加入</span>', rendered)


class DedupeTwinPostTests(unittest.TestCase):
    """同一篇貼文重貼到 IG／Threads／FB，抽出的活動要收成一場。"""

    RECRUIT = "社團博覽會擺攤資訊：陽明交大 9/9 工三前草坪，清華大學 9/10 新體育館旁 L 型馬路，歡迎來聊聊"
    SHOWCASE = "本週兩齣戲同時開演，A 廳與 B 廳各一場，散場後有演後座談，歡迎留下來聊聊你的想法"

    def event(self, eid, title, source_id, post_id, start="2026-09-09T17:30:00+08:00", **kw):
        ev = {
            "id": eid, "title": title, "start_at": start, "end_at": None, "all_day": False,
            "venue": "工三前草坪", "school": "nycu",
            "source": {"platform": source_id.split("_")[0], "source_id": source_id,
                       "post_id": post_id, "url": f"https://example.com/{post_id}"},
            "extraction": {"confidence": 0.8},
        }
        ev.update(kw)
        return ev

    def dedupe(self, events, texts):
        with mock.patch.object(build_site, "_post_norm_texts", return_value=texts):
            return build_site.dedupe(events)

    def test_cross_platform_repost_merges_despite_unrelated_titles(self):
        fb = self.event("evt_fb", "丁未梅竹籌備委員會徵才｜陽明交大社團博覽會", "fb_meichu", "p1")
        ig = self.event("evt_ig", "梅竹籌備委員會徵才說明", "ig_meichu", "p2")

        out = self.dedupe([fb, ig], {("fb_meichu", "p1"): "前情提要" + self.RECRUIT,
                                     ("ig_meichu", "p2"): self.RECRUIT})

        self.assertEqual([e["id"] for e in out], ["evt_fb"])
        self.assertEqual([p["source_id"] for p in out[0]["alt_posts"]], ["ig_meichu"])

    def test_unrelated_posts_at_the_same_slot_stay_separate(self):
        a = self.event("evt_a", "梅竹籌備委員會徵才說明", "ig_meichu", "p1")
        b = self.event("evt_b", "美術社社博攤位", "ig_art", "p2")

        out = self.dedupe([a, b], {("ig_meichu", "p1"): self.RECRUIT,
                                   ("ig_art", "p2"): self.SHOWCASE})

        self.assertEqual(sorted(e["id"] for e in out), ["evt_a", "evt_b"])

    def test_sessions_from_one_post_never_collapse(self):
        a = self.event("evt_a", "《別照鏡子》晚場", "ig_drama", "p1", venue="A 廳")
        b = self.event("evt_b", "《樂園混音》晚場", "ig_drama", "p1", venue="B 廳")

        out = self.dedupe([a, b], {("ig_drama", "p1"): self.SHOWCASE})

        self.assertEqual(sorted(e["id"] for e in out), ["evt_a", "evt_b"])

    def test_twinned_multi_session_posts_pair_up_one_to_one(self):
        texts = {("ig_drama", "p1"): self.SHOWCASE, ("fb_drama", "p2"): self.SHOWCASE}
        events = [
            self.event("evt_ig_a", "《別照鏡子》晚場", "ig_drama", "p1", venue="A 廳"),
            self.event("evt_ig_b", "《樂園混音》晚場", "ig_drama", "p1", venue="B 廳"),
            self.event("evt_fb_a", "別照鏡子 晚間場次", "fb_drama", "p2", venue="A 廳"),
            self.event("evt_fb_b", "樂園混音 晚間場次", "fb_drama", "p2", venue="B 廳"),
        ]

        out = self.dedupe(events, texts)

        self.assertEqual(len(out), 2)
        merged = {e["title"]: [p["post_id"] for p in e.get("alt_posts", [])] for e in out}
        self.assertEqual(sorted(merged), ["《別照鏡子》晚場", "《樂園混音》晚場"])
        self.assertEqual(merged["《別照鏡子》晚場"], ["p2"])
        self.assertEqual(merged["《樂園混音》晚場"], ["p2"])

    def test_short_posts_are_not_treated_as_twins(self):
        a = self.event("evt_a", "口琴社社課", "ig_a", "p1")
        b = self.event("evt_b", "吉他社社課", "ig_b", "p2")

        out = self.dedupe([a, b], {})  # 太短的貼文不進比對表

        self.assertEqual(sorted(e["id"] for e in out), ["evt_a", "evt_b"])


class DedupeDistinctSessionTests(unittest.TestCase):
    """抽取器刻意拆開的多場次，不可以被當成重複收掉。"""

    def event(self, eid, title, post_id, start, organizer="陽明交大學生會陽明分會",
              source_id="ig_ymsa", venue=None):
        return {
            "id": eid, "title": title, "start_at": start, "end_at": None, "all_day": False,
            "venue": venue, "school": "nycu", "organizer": organizer,
            "source": {"platform": "instagram", "source_id": source_id, "post_id": post_id,
                       "url": f"https://example.com/{post_id}"},
            "extraction": {"confidence": 0.8},
        }

    def dedupe(self, events):
        with mock.patch.object(build_site, "_post_norm_texts", return_value={}):
            return build_site.dedupe(events)

    def test_sessions_listed_in_one_post_survive_near_identical_titles(self):
        events = [
            self.event("evt_a", "第33屆陽明分會選舉實體投票（活四）", "p1",
                       "2026-05-11T11:00:00+08:00", venue="活動中心四樓"),
            self.event("evt_b", "第33屆陽明分會選舉實體投票（人社院）", "p1",
                       "2026-05-11T11:30:00+08:00", venue="人社院"),
        ]

        self.assertEqual(sorted(e["id"] for e in self.dedupe(events)), ["evt_a", "evt_b"])

    def test_one_post_listing_two_clubs_at_the_same_slot_stays_split(self):
        events = [
            self.event("evt_a", "EMBA 羽球社社課", "p1", "2026-03-05T16:00:00+08:00"),
            self.event("evt_b", "EMBA 桌球社社課", "p1", "2026-03-05T16:00:00+08:00"),
        ]

        self.assertEqual(sorted(e["id"] for e in self.dedupe(events)), ["evt_a", "evt_b"])

    def test_different_clubs_booths_at_one_fair_stay_split(self):
        """剝掉各自的社名後核心同為「社團博覽會攤位」，但那是兩個社團的兩個攤位。"""
        events = [
            self.event("evt_a", "社團博覽會｜關懷生命社攤位", "p1", "2026-08-31T11:00:00+08:00",
                       organizer="陽明關懷生命社", source_id="ig_dogs"),
            self.event("evt_b", "愛杏管弦樂團社團博覽會攤位", "p2", "2026-08-31T11:00:00+08:00",
                       organizer="陽明愛杏管弦樂團", source_id="fb_aising"),
        ]

        self.assertEqual(sorted(e["id"] for e in self.dedupe(events)), ["evt_a", "evt_b"])

    def test_same_organizer_written_two_ways_still_merges(self):
        events = [
            self.event("evt_a", "清大鋼琴社春季音樂會", "p1", "2026-05-14T19:00:00+08:00",
                       organizer="清大鋼琴社", source_id="ig_piano"),
            self.event("evt_b", "鋼琴社春季音樂會", "p2", "2026-05-14T19:00:00+08:00",
                       organizer="清大鋼琴社", source_id="fb_piano"),
        ]

        self.assertEqual([e["id"] for e in self.dedupe(events)], ["evt_a"])


class FeedPlatformBadgeTests(unittest.TestCase):
    """河道貼文右上角：平台標誌，點了到來源帳號主頁。"""

    ENTRY = {"id": 7, "name": "陽明游泳社",
             "sids": ["ig_ymswim", "fb_ymswimmingclub"],
             "links": [{"platform": "instagram", "url": "https://www.instagram.com/ymswim/"},
                       {"platform": "facebook", "url": "https://www.facebook.com/YMswimmingclub"}]}

    def test_profile_url_prefers_the_directory_link_for_that_source(self):
        self.assertEqual(build_site.profile_url("fb_ymswimmingclub", "facebook", self.ENTRY),
                         "https://www.facebook.com/YMswimmingclub")
        self.assertEqual(build_site.profile_url("ig_ymswim", "instagram", self.ENTRY),
                         "https://www.instagram.com/ymswim/")

    def test_api_source_links_to_the_site_root_not_the_endpoint(self):
        entry = {"sids": ["nycu_life_api"],
                 "links": [{"platform": "bulletin", "url": "https://events.life.nycu.edu.tw/api/activities"}]}
        self.assertEqual(build_site.profile_url("nycu_life_api", "api", entry), "https://events.life.nycu.edu.tw/")

    def test_profile_url_falls_back_to_the_platform_handle(self):
        self.assertEqual(build_site.profile_url("threads_nthu_sa", "threads", None),
                         "https://www.threads.com/@nthu_sa")
        self.assertIsNone(build_site.profile_url("infonews_lecture", "bulletin", None))

    def test_row_shows_platform_logo_linking_to_the_profile(self):
        post = {"source_id": "ig_ymswim", "post_id": "p1", "source_name": "陽明游泳社", "platform": "instagram",
                "school": "nycu", "campus": "yangming", "url": "https://www.instagram.com/p/p1/",
                "profile_url": "https://www.instagram.com/ymswim/", "posted_at": "2026-09-01T10:00:00+08:00",
                "text": "社課", "image": None, "avatar": None, "org_id": 7, "events": []}
        html = build_site._feed_row(post, build_site._iso_dt("2026-09-02T10:00:00+08:00"))
        self.assertIn('<a class="feed-plat" href="https://www.instagram.com/ymswim/" target="_blank"', html)
        self.assertIn('aria-label="陽明游泳社的 Instagram 主頁"', html)
        self.assertIn(build_site.FEED_PLAT_ICON["instagram"], html)
        self.assertNotIn("post-menu", html)

    def test_bulletin_without_profile_shows_a_plain_badge(self):
        post = {"source_id": "nthu_bulletin", "post_id": "b1", "source_name": "清大公告", "platform": "bulletin",
                "school": "nthu", "campus": None, "url": None, "profile_url": None,
                "posted_at": "2026-09-01T10:00:00+08:00", "text": "公告", "image": None, "avatar": None,
                "org_id": 3, "events": []}
        html = build_site._feed_row(post, build_site._iso_dt("2026-09-02T10:00:00+08:00"))
        self.assertIn('<span class="feed-plat" title="公告頁">', html)
        self.assertNotIn('<a class="feed-plat"', html)


class FeedPrerenderTests(unittest.TestCase):
    """首頁 SSR 的分欄要跟 app.js computeBuckets() 一樣，JS 接手時才不會跳版。"""

    def post(self, pid, school, campus=None, name="", events=()):
        return {"source_id": "ig_x", "post_id": pid, "source_name": name, "platform": "instagram",
                "school": school, "campus": campus, "url": None, "posted_at": "2026-09-01T10:00:00+08:00",
                "text": "t", "image": None, "avatar": None, "org_id": 1, "events": list(events)}

    def test_school_buckets_split_by_campus_and_rotate_cross_school_posts(self):
        posts = [self.post("a", "nycu", "guangfu"), self.post("b", "nthu"), self.post("c", "nycu", "yangming"),
                 self.post("d", "both"), self.post("e", "both"), self.post("f", "nycu", None, name="陽明有氧社"),
                 self.post("g", "nycu", None, name="不明單位")]
        gf, nthu, ym = build_site.feed_school_buckets(posts)
        ids = lambda b: [p["post_id"] for p in b]
        self.assertEqual(ids(gf), ["a", "d", "g"])       # 交大欄：交大＋第一則跨校＋校區不明的交大貼文
        self.assertEqual(ids(nthu), ["b", "e"])          # 清大欄：清大＋第二則跨校
        self.assertEqual(ids(ym), ["c", "f", "g"])       # 陽明欄：陽明＋名稱判定＋校區不明的也放

    def test_row_reserves_image_box_when_size_known(self):
        p = self.post("a", "nthu"); p.update({"image": "/assets/posts/x.jpg", "image_w": 1200, "image_h": 800})
        html = build_site._feed_row(p, build_site._iso_dt("2026-09-02T10:00:00+08:00"))
        self.assertIn('<img class="feed-img" src="/assets/posts/x.jpg" alt="" width="1200" height="800" loading="lazy">', html)

    def test_prerender_writes_deck_and_pager_variants(self):
        posts = [self.post("a", "nycu", "guangfu"), self.post("b", "nthu"), self.post("c", "nycu", "yangming")]
        index = Path(tempfile.mkdtemp()) / "index.html"
        index.write_text('<div id="post-feed"><!-- ssr-feed --><!-- /ssr-feed --></div>')
        with mock.patch.object(build_site, "SITE", index.parent):
            build_site.prerender_feed(posts)
        out = index.read_text()
        self.assertIn('class="feed-cols ssr-deck has-deck-add" style="--ncols:3"', out)
        self.assertIn('class="feed-cols ssr-pager" style="--ncols:1"', out)
        self.assertEqual(out.count('<section class="feed-col"'), 4)
        self.assertIn('<h2>交大</h2>', out)
        self.assertIn('class="deck-add"', out)


class DedupeDeterminismTests(unittest.TestCase):
    def test_title_core_strips_the_same_prefix_every_run(self):
        """走訪 set 會受 hash 隨機化影響，同一份輸入不能每次 build 得到不同結果。"""
        events = [
            {"id": "evt_a", "title": "清大鋼琴社春季音樂會", "start_at": "2026-05-14T19:00:00+08:00",
             "all_day": False, "venue": "大禮堂", "organizer": "清大鋼琴社", "school": "nthu",
             "source": {"platform": "instagram", "source_id": "ig_piano", "post_id": "p1",
                        "url": "https://example.com/p1"},
             "extraction": {"confidence": 0.8}},
            {"id": "evt_b", "title": "春季音樂會", "start_at": "2026-05-14T19:00:00+08:00",
             "all_day": False, "venue": "大禮堂", "organizer": "清大鋼琴社", "school": "nthu",
             "source": {"platform": "facebook", "source_id": "fb_piano", "post_id": "p2",
                        "url": "https://example.com/p2"},
             "extraction": {"confidence": 0.7}},
        ]
        with mock.patch.object(build_site, "_post_norm_texts", return_value={}):
            runs = {tuple(e["id"] for e in build_site.dedupe(copy.deepcopy(events)))
                    for _ in range(5)}

        self.assertEqual(runs, {("evt_a",)})


if __name__ == "__main__":
    unittest.main()
