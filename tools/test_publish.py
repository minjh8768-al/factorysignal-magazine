# -*- coding: utf-8 -*-
"""카드 생성·인덱스 교체 단위테스트."""
import os
import re
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


class Coverage(unittest.TestCase):
    """'6종 1개씩'이 목표라 배치가 어떤 카테고리를 덮었는지 알려준다."""

    def _report(self, cats):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            publish.report_coverage(cats)
        return buf.getvalue()

    def test_full_batch_has_no_warnings(self):
        out = self._report(list(article.CATEGORIES))
        self.assertNotIn("빠진 카테고리", out)
        self.assertNotIn("중복", out)

    def test_reports_missing(self):
        out = self._report(["정치", "경제"])
        self.assertIn("빠진 카테고리", out)
        for cat in ("암호화폐", "스포츠", "세계", "스타트업"):
            self.assertIn(cat, out)

    def test_reports_duplicates(self):
        out = self._report(["정치", "정치", "경제"])
        self.assertIn("중복", out)
        self.assertIn("정치×2", out)

    def test_empty_batch(self):
        self.assertIn("없음", self._report([]))


class BatchFlags(unittest.TestCase):
    """draft.py --check 와 publish.py --apply --en 이 흐름을 이어 붙인다."""

    def test_publish_accepts_translate_flag(self):
        import inspect
        sig = inspect.signature(publish.do_publish)
        self.assertIn("translate_too", sig.parameters)
        self.assertFalse(sig.parameters["translate_too"].default)

    def test_main_maps_en_flag(self):
        import inspect
        src = inspect.getsource(publish.main)
        self.assertIn('translate_too="--en" in args', src)

    def test_draft_check_flag_runs_factcheck(self):
        import inspect
        import draft
        src = inspect.getsource(draft.main)
        self.assertIn('"--check" in argv', src)
        self.assertIn("factcheck", src)

    def test_en_flag_is_not_treated_as_a_slug(self):
        # --로 시작하는 인자는 slug 목록에서 빠져야 한다
        import inspect
        src = inspect.getsource(publish.main)
        self.assertIn('not a.startswith("--")', src)


class TemplateDrift(unittest.TestCase):
    """article.py의 nav·footer 템플릿이 실제 사이트와 어긋나지 않았는지.

    2026-08-04에 동료가 사이트의 모든 기사 nav에 Factory Holdings 링크와 텔레그램
    버튼을 추가했는데, article.py의 _NAV은 그대로였다. 그 상태로 새 기사를 만들면
    그 기사만 링크가 빠진다. 손으로 고친 사이트와 생성 템플릿이 갈라지는 것은
    이 구조에서 언제든 다시 일어날 수 있으므로 테스트로 잡는다.
    """

    INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "articles", "index.html")

    def _block(self, text, pattern):
        m = re.search(pattern, text, re.S)
        self.assertIsNotNone(m, f"블록을 찾지 못했습니다: {pattern}")
        return m.group(0)

    def test_nav_links_match_site(self):
        with open(self.INDEX, encoding="utf-8") as f:
            live = f.read()
        pattern = r'  <div class="nav-links">\n.*?\n  </div>'
        self.assertEqual(
            self._block(article._NAV, pattern),
            self._block(live, pattern),
            "article.py의 _NAV이 articles/index.html의 nav와 다릅니다. "
            "사이트를 손으로 고쳤다면 템플릿에도 반영하세요.")

    def test_footer_brand_text_matches_site(self):
        with open(self.INDEX, encoding="utf-8") as f:
            live = f.read()
        pattern = r'<p class="footer-tagline">.*?</p>'
        self.assertEqual(self._block(article._FOOTER, pattern),
                         self._block(live, pattern))


class EnglishPairs(unittest.TestCase):
    """영어판은 카드를 만들지 않고, 삭제할 때는 함께 지운다."""

    def test_english_page_has_no_publish_date(self):
        # publish.published()는 fs:date가 있는 파일만 카드로 만든다.
        # translate.py는 fs:date를 심지 않으므로 영어판은 카드가 생기지 않는다.
        import translate
        ko = {"slug": "x", "category": "정치", "read": "8", "video": "abcdefghijk",
              "source_title": "SBS", "title": "제목", "description": "설명",
              "eyebrow": "Politics", "date": "2026-08-03"}
        en = {"title": "Title", "description": "Desc", "eyebrow": "Politics",
              "body_html": "<p>Body</p>"}
        out = translate.render_en(ko, en)
        self.assertNotIn('name="fs:date"', out)
        self.assertIn('name="fs:lang" content="en"', out)
        self.assertIn('<html lang="en">', out)

    def test_english_page_links_back_and_declares_alternate(self):
        import translate
        ko = {"slug": "fomc", "category": "경제", "read": "8", "video": "abcdefghijk",
              "source_title": "KBS", "title": "제목", "description": "설명",
              "eyebrow": "Market Watch", "date": "2026-08-03"}
        en = {"title": "Fed holds", "description": "Desc", "eyebrow": "Market Watch",
              "body_html": "<p>Body</p>"}
        out = translate.render_en(ko, en)
        self.assertIn('hreflang="ko" href="fomc.html"', out)
        self.assertIn('href="fomc.html" class="lang-switch"', out)

    def test_investment_disclaimer_only_for_money_categories(self):
        import translate
        base = {"slug": "x", "read": "8", "video": "abcdefghijk", "source_title": "S",
                "title": "t", "description": "d", "eyebrow": "E", "date": "2026-08-03"}
        en = {"title": "T", "description": "D", "eyebrow": "E",
              "body_html": "<p>Body</p>"}
        for cat in ("경제", "암호화폐"):
            self.assertIn("not investment advice",
                          translate.render_en(dict(base, category=cat), en))
        for cat in ("정치", "스포츠", "세계", "스타트업"):
            self.assertNotIn("not investment advice",
                             translate.render_en(dict(base, category=cat), en))


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
