# -*- coding: utf-8 -*-
"""카드 생성·인덱스 교체 단위테스트."""
import os
import tempfile
import unittest

import article
import publish

META = {
    "slug": "fomc-rate-freeze",
    "category": "경제",
    "eyebrow": "Market Watch",
    "title": 'FOMC, 금리 동결…"떠나지 마라"',
    "description": "김영익 교수가 본 금리와 증시.",
    "read": "8",
    "video": "xpYSG58n7Tg",
}

INDEX = """<div class="article-grid">
          <!-- CARDS:START --><!-- CARDS:END -->

          <a href="why-signal-token.html" class="article-card" data-category="암호화폐">
            <div class="article-thumb"><span>TOKEN</span></div>
          </a>
        </div>"""


class Card(unittest.TestCase):
    def test_data_category_is_the_only_color_source(self):
        card = article.card_html(META)
        self.assertIn('data-category="경제"', card)
        # 색을 파이썬에서 넣지 않는다 (CSS가 data-category로 붙인다)
        self.assertNotIn("#0ea968", card)
        self.assertNotIn("linear-gradient", card)

    def test_uses_youtube_thumbnail(self):
        card = article.card_html(META)
        self.assertIn("article-thumb--video", card)
        self.assertIn("img.youtube.com/vi/xpYSG58n7Tg/hqdefault.jpg", card)

    def test_escapes_quotes_in_title(self):
        card = article.card_html(META)
        self.assertIn("&quot;", card)
        self.assertNotIn('<h3>FOMC, 금리 동결…"', card)

    def test_bad_category_rejected(self):
        with self.assertRaises(ValueError):
            article.card_html(dict(META, category="연예"))


class ReplaceCards(unittest.TestCase):
    def test_inserts_between_markers(self):
        out = article.replace_cards(INDEX, [article.card_html(META)])
        self.assertIn("fomc-rate-freeze.html", out)
        head, _, tail = out.partition(article.CARDS_START)
        self.assertIn('<div class="article-grid">', head)
        self.assertIn(article.CARDS_END, tail)

    def test_does_not_touch_handwritten_cards(self):
        out = article.replace_cards(INDEX, [article.card_html(META)])
        self.assertIn('<a href="why-signal-token.html" class="article-card"'
                      ' data-category="암호화폐">', out)
        self.assertIn('<div class="article-thumb"><span>TOKEN</span></div>', out)

    def test_empty_list_clears_block_only(self):
        filled = article.replace_cards(INDEX, [article.card_html(META)])
        cleared = article.replace_cards(filled, [])
        self.assertNotIn("fomc-rate-freeze", cleared)
        self.assertIn("why-signal-token.html", cleared)
        self.assertEqual(cleared.count(article.CARDS_START), 1)

    def test_rebuild_is_idempotent(self):
        once = article.replace_cards(INDEX, [article.card_html(META)])
        twice = article.replace_cards(once, [article.card_html(META)])
        self.assertEqual(once, twice)

    def test_missing_markers_raise(self):
        with self.assertRaises(ValueError) as cm:
            article.replace_cards('<div class="article-grid"></div>', [])
        self.assertIn("마커가 없습니다", str(cm.exception))


class StripFactcheck(unittest.TestCase):
    """검수 메모는 발행본에 남지 않아야 한다."""

    DOC = ('<!DOCTYPE html>\n'
           '<!-- FACTCHECK:START\n'
           '     !! [인물] 곽상원 의원 — 근거 67건뿐\n'
           '     FACTCHECK:END -->\n'
           '<html lang="ko">\n<head>\n</head>\n</html>\n')

    def test_removes_block(self):
        out = publish.strip_factcheck(self.DOC)
        self.assertNotIn("FACTCHECK", out)
        self.assertNotIn("곽상원", out)
        self.assertTrue(out.startswith("<!DOCTYPE html>\n<html lang=\"ko\">"))

    def test_noop_without_block(self):
        plain = '<!DOCTYPE html>\n<html lang="ko">\n</html>\n'
        self.assertEqual(publish.strip_factcheck(plain), plain)

    def test_idempotent(self):
        once = publish.strip_factcheck(self.DOC)
        self.assertEqual(publish.strip_factcheck(once), once)


class TitleRoundTrip(unittest.TestCase):
    """render()가 붙인 제목 접미사를 publish가 정확히 떼는지.

    2026-08-03 리브랜딩 때 두 곳에 브랜드명이 따로 박혀 있어 카드 제목에
    " — Factory Magazine"이 남는 버그가 났다. 그 재발을 막는 테스트다.
    """

    FIELDS = {
        "title": '민주당 주도 형소법 개정안 통과…정치권 "전리품" 평가',
        "description": "70년 만의 검찰 수사권 폐지.",
        "slug": "criminal-procedure-act-passed",
        "category": "정치",
        "eyebrow": "Politics",
        "read_minutes": 8,
        "source_title": "SBS 뉴스 · 정치사냥꾼",
        "body_html": "<p>본문</p>",
    }
    URL = "https://www.youtube.com/watch?v=LZcHNBmWzaY"

    def _parse(self, html_text):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html_text)
            return publish.read_meta(path)

    def test_title_suffix_is_stripped(self):
        meta = self._parse(article.render(dict(self.FIELDS), self.URL))
        self.assertEqual(meta["title"], self.FIELDS["title"])
        self.assertNotIn(article.BRAND, meta["title"])

    def test_all_card_fields_survive(self):
        meta = self._parse(article.render(dict(self.FIELDS), self.URL))
        self.assertEqual(meta["category"], "정치")
        self.assertEqual(meta["eyebrow"], "Politics")
        self.assertEqual(meta["read"], "8")
        self.assertEqual(meta["video"], "LZcHNBmWzaY")
        self.assertEqual(meta["description"], self.FIELDS["description"])

    def test_card_built_from_parsed_meta_has_no_brand_suffix(self):
        meta = self._parse(article.render(dict(self.FIELDS), self.URL))
        card = article.card_html(dict(meta, slug=self.FIELDS["slug"]))
        self.assertNotIn(f"{article.TITLE_SUFFIX}</h3>", card)
        self.assertIn("<h3>민주당 주도", card)

    def test_byline_uses_shared_constant(self):
        rendered = article.render(dict(self.FIELDS), self.URL)
        card = article.card_html(dict(META))
        for text in (rendered, card):
            self.assertIn(article.BYLINE, text)


if __name__ == "__main__":
    unittest.main()
