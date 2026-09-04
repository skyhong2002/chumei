import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_nycu_open_data import detail_api_url, parse_content, parse_list


class NYCUOpenDataTests(unittest.TestCase):
    def test_parses_serno_title_and_roc_update_date(self):
        page_url = "https://osa.nycu.edu.tw/osa/ch/app/data/list?id=3494&module=nycu0085"
        document = """
        <div class="newslist"><ul><li>
          <a href="/osa/ch/app/data/view?module=nycu0085&amp;id=3494&amp;serno=abc-123"
             title="抓馬劇場工作坊">
            <div class="info"><p>更新日期：115-09-02</p><p>分類：校內活動</p></div>
            <p>抓馬劇場工作坊</p>
          </a>
        </li></ul></div>
        """
        self.assertEqual(parse_list(document, page_url), [{
            "post_id": "abc-123",
            "url": "https://osa.nycu.edu.tw/osa/ch/app/data/view?module=nycu0085&id=3494&serno=abc-123",
            "title": "抓馬劇場工作坊",
            "posted_at": "2026-09-02T00:00:00+08:00",
        }])

    def test_builds_official_json_url_and_extracts_content_images(self):
        detail = "https://osa.nycu.edu.tw/osa/ch/app/data/view?module=m&id=1&serno=abc"
        self.assertEqual(
            detail_api_url(detail),
            "https://osa.nycu.edu.tw/osa/ch/app/openData/data/data?module=m&id=1&serno=abc&type=json",
        )
        text, images = parse_content(
            '<div>第一行<br>第二行<img src="/poster.png"></div>', detail
        )
        self.assertEqual(text, "第一行\n第二行")
        self.assertEqual(images, ["https://osa.nycu.edu.tw/poster.png"])


if __name__ == "__main__":
    unittest.main()
