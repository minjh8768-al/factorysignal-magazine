# -*- coding: utf-8 -*-
"""article.py 단위테스트. 네트워크 없음.

    cd tools && py -3 -m unittest discover -p "test_*.py" -v
"""
import unittest

import article

FIELDS = {
    "title": '"보완수사권 폐지" 국회 통과',
    "description": "본회의를 통과한 법안의 쟁점을 정리했다.",
    "slug": "supplementary-investigation",
    "category": "정치",
    "eyebrow": "Policy Watch",
    "read_minutes": 6,
    "source_title": "SBS 뉴스 · 정치사냥꾼",
    "body_html": "<p>본문</p><h2>쟁점</h2><p>내용</p>",
}
URL = "https://www.youtube.com/watch?v=LZcHNBmWzaY"


class VideoId(unittest.TestCase):
    def test_url_forms_give_same_id(self):
        for url in (
            "https://youtu.be/LZcHNBmWzaY",
            "https://www.youtube.com/watch?v=LZcHNBmWzaY",
            "https://www.youtube.com/watch?v=LZcHNBmWzaY&t=10s",
            "https://www.youtube.com/watch?t=10&v=LZcHNBmWzaY&list=PLx",
            "https://www.youtube.com/shorts/LZcHNBmWzaY",
            "https://www.youtube.com/embed/LZcHNBmWzaY",
        ):
            self.assertEqual(article.video_id(url), "LZcHNBmWzaY", url)

    def test_rejects_non_youtube(self):
        with self.assertRaises(ValueError):
            article.video_id("https://example.com/watch?v=abc")


class BodyValidation(unittest.TestCase):
    def test_allowed_tags_pass(self):
        body = ("<p>단락</p><h2>소제목</h2><blockquote>인용</blockquote>"
                "<ul><li><strong>강조</strong></li></ul>"
                '<p><a href="https://example.com">링크</a></p>')
        self.assertEqual(article.validate_body(body), body)

    def test_script_rejected(self):
        with self.assertRaises(ValueError) as cm:
            article.validate_body("<p>a</p><script>alert(1)</script>")
        self.assertIn("script", str(cm.exception))

    def test_div_and_img_rejected(self):
        for bad in ("<div>x</div>", '<img src="x.png" />', "<h1>제목</h1>"):
            with self.assertRaises(ValueError):
                article.validate_body(bad)

    def test_javascript_href_rejected(self):
        with self.assertRaises(ValueError):
            article.validate_body('<p><a href="javascript:alert(1)">x</a></p>')

    def test_truncated_body_rejected(self):
        # 실측 사고: 출력 상한에 걸려 본문이 문장 중간에서 끊겼는데도 통과했다
        with self.assertRaises(ValueError) as cm:
            article.validate_body("<p>완결된 단락</p><p>중간에서 끊긴 문장,")
        self.assertIn("잘렸을 수", str(cm.exception))

    def test_unclosed_list_rejected(self):
        with self.assertRaises(ValueError):
            article.validate_body("<ul><li>하나</li><li>둘</li>")

    def test_mismatched_close_rejected(self):
        with self.assertRaises(ValueError):
            article.validate_body("<p>글</h2>")

    def test_br_needs_no_closing_tag(self):
        for body in ("<p>줄<br>바꿈</p>", "<p>줄<br />바꿈</p>"):
            self.assertEqual(article.validate_body(body), body)


class CategoryValidation(unittest.TestCase):
    def test_six_categories_pass(self):
        for cat in ("정치", "경제", "암호화폐", "스포츠", "세계", "스타트업"):
            self.assertEqual(article.validate_category(cat), cat)

    def test_other_value_rejected(self):
        for bad in ("연예", "Politics", "", "정치 "):
            with self.assertRaises(ValueError):
                article.validate_category(bad)


class Slug(unittest.TestCase):
    def test_normalises(self):
        self.assertEqual(article.clean_slug("Assembly Bill Passed!"),
                         "assembly-bill-passed")
        self.assertEqual(article.clean_slug("--a__b--"), "a-b")

    def test_unusable_slug_raises(self):
        for bad in ("", "한글만", "!!!"):
            with self.assertRaises(ValueError):
                article.clean_slug(bad)


class TidyBody(unittest.TestCase):
    def test_one_line_body_gets_line_per_block(self):
        out = article.tidy_body("<p>a</p><h2>b</h2><p>c</p>")
        self.assertEqual(out, "  <p>a</p>\n  <h2>b</h2>\n  <p>c</p>")

    def test_list_items_split(self):
        out = article.tidy_body("<ul><li>x</li><li>y</li></ul>")
        self.assertEqual(out.count("\n"), 3)

    def test_inline_tags_stay_on_their_line(self):
        out = article.tidy_body("<p>a <strong>b</strong> c</p>")
        self.assertEqual(out, "  <p>a <strong>b</strong> c</p>")


class Disclaimer(unittest.TestCase):
    def test_money_categories_warn_about_loss(self):
        for cat in ("암호화폐", "경제"):
            self.assertIn("원금 손실", article.disclaimer_for(cat))

    def test_other_categories_do_not(self):
        for cat in ("정치", "세계", "스포츠", "스타트업"):
            self.assertNotIn("원금 손실", article.disclaimer_for(cat))

    def test_all_categories_disclaim_endorsement(self):
        for cat in article.CATEGORIES:
            self.assertIn("검증하거나 보증하는", article.disclaimer_for(cat))


class Render(unittest.TestCase):
    def setUp(self):
        self.html = article.render(dict(FIELDS), URL)

    def test_metadata_survives_round_trip(self):
        for expected in ('<meta name="fs:category" content="정치" />',
                         '<meta name="fs:eyebrow" content="Policy Watch" />',
                         '<meta name="fs:read" content="6" />',
                         '<meta name="fs:video" content="LZcHNBmWzaY" />'):
            self.assertIn(expected, self.html)

    def test_embeds_video_and_source_link(self):
        self.assertIn("https://www.youtube.com/embed/LZcHNBmWzaY", self.html)
        self.assertIn("https://www.youtube.com/watch?v=LZcHNBmWzaY", self.html)
        self.assertIn("요약·정리한 것입니다", self.html)

    def test_body_blocks_preserved_one_per_line(self):
        # 내용은 그대로 남고, 검수용으로 블록마다 줄이 나뉜다
        self.assertIn("\n  <p>본문</p>\n  <h2>쟁점</h2>\n  <p>내용</p>\n", self.html)

    def test_css_path_matches_articles_depth(self):
        # _drafts/ 와 articles/ 는 같은 깊이라 이 경로가 양쪽에서 유효해야 한다
        self.assertIn('href="../css/style.css"', self.html)

    def test_quotes_in_title_are_escaped_in_meta(self):
        # 제목에 큰따옴표가 있어도 description/meta 속성이 깨지지 않아야 한다
        self.assertIn("&quot;", self.html)
        self.assertNotIn('content=""보완', self.html)

    def test_politics_article_has_no_investment_warning(self):
        self.assertNotIn("원금 손실", self.html)

    def test_bad_category_stops_render(self):
        bad = dict(FIELDS, category="연예")
        with self.assertRaises(ValueError):
            article.render(bad, URL)

    def test_bad_tag_stops_render(self):
        bad = dict(FIELDS, body_html="<p>a</p><script>x</script>")
        with self.assertRaises(ValueError):
            article.render(bad, URL)


if __name__ == "__main__":
    unittest.main()
