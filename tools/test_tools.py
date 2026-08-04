# -*- coding: utf-8 -*-
"""collect.py · factcheck.py · naver.py 단위테스트. 네트워크 없음."""
import unittest

import collect
import factcheck
import naver


class Duration(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(collect.duration_seconds("12:51"), 771)
        self.assertEqual(collect.duration_seconds("1:02:03"), 3723)
        self.assertEqual(collect.duration_seconds("0:45"), 45)

    def test_rejects_non_duration(self):
        for bad in ("", None, "라이브", "실시간 스트리밍", "12"):
            self.assertIsNone(collect.duration_seconds(bad))


def video(title="제목", channel="채널", length="12:00", published="1일 전", vid="abcdefghijk"):
    return {"id": vid, "title": title, "channel": channel,
            "length": length, "published": published}


class Filter(unittest.TestCase):
    def test_keeps_normal_recent_video(self):
        self.assertTrue(collect.keep(video(), False))

    def test_drops_betting_content(self):
        # 실측: 스포츠 1차 검색이 전부 승부예측 채널이었다
        for bad in ("8/2 국야분석.국내야구분석.KBO분석",
                    "NPB 일본야구 경기분석 승부예측",
                    "AI 승리팀 예측! 정확한 적중률"):
            self.assertFalse(collect.keep(video(title=bad), False), bad)

    def test_drops_flagged_channels(self):
        for ch in ("Why Times", "스작TV-Sports Anal", "KBO Diamond 24H", "노마-스포차TV",
                   "뉴스 247", "한국시사TV", "뉴스브리핑TV"):
            self.assertFalse(collect.keep(video(channel=ch), False), ch)

    def test_drops_clickbait_investment_titles(self):
        # 실측: 암호화폐 후보가 전부 개인 트레이딩 채널의 낚시성 제목이었다
        for bad in ("비트코인 한 달간 이렇게 하세요",
                    "8월 폭등 온다",
                    "지금 사야 하는 이유",
                    "[야구여왕2] 감독이 끝까지 숨긴 비밀병기"):
            self.assertFalse(collect.keep(video(title=bad), False), bad)

    def test_keeps_legitimate_news_title(self):
        for good in ("[단독] 벤투 \"축구대표팀 임시 감독직 지원 안 한다\"",
                     "요동치는 민심 흔들리는 권력 (KBS_2026.07.25.방송)",
                     "[긴급분석] FOMC 금리동결과 출렁이는 국내증시"):
            self.assertTrue(collect.keep(video(title=good), False), good)

    def test_drops_too_short_and_too_long(self):
        self.assertFalse(collect.keep(video(length="2:30"), False))
        self.assertFalse(collect.keep(video(length="41:00"), False))

    def test_recency_strict_vs_loose(self):
        old = video(published="3개월 전")
        self.assertFalse(collect.keep(old, False))     # 시사 카테고리
        self.assertTrue(collect.keep(old, True))       # 스타트업은 허용
        self.assertFalse(collect.keep(video(published="3년 전"), True))

    def test_drops_missing_id(self):
        self.assertFalse(collect.keep(video(vid=None), False))

    def test_every_category_has_queries(self):
        import article
        self.assertEqual(set(collect.QUERIES), set(article.CATEGORIES))
        for cat, qs in collect.QUERIES.items():
            self.assertTrue(qs, cat)


class Extract(unittest.TestCase):
    def test_person_with_title(self):
        got = factcheck.extract("곽상언 의원만이 유일하게 반대표를 던졌다.")
        self.assertIn(("인물", "곽상언 의원", '"곽상언" 의원'), got)

    def test_person_with_org_title(self):
        got = [w for k, w, _ in factcheck.extract(
            "정광재 동연정치연구소장은 우려를 표했다.") if k == "인물"]
        self.assertIn("정광재 동연정치연구소장", got)

    def test_dates(self):
        got = [w for k, w, _ in factcheck.extract(
            "2026년 1월 15일에 치러진 대선. 8월 17일 전당대회. 2025년 시위.") if k == "날짜"]
        self.assertIn("8월 17일", got)
        self.assertTrue(any("2026년" in g for g in got))

    def test_numbers_worth_checking(self):
        got = [w for k, w, _ in factcheck.extract(
            "71.65%의 득표율로 승리했다. 찬성 175표. 참가자 120명.") if k == "수치"]
        self.assertIn("71.65%", got)
        self.assertIn("175표", got)
        self.assertIn("120명", got)

    def test_ignores_plain_numbers(self):
        got = [w for k, w, _ in factcheck.extract("3개 항목과 5가지 이유.") if k == "수치"]
        self.assertEqual(got, [])

    def test_deduplicates(self):
        got = factcheck.extract("곽상언 의원. 다시 곽상언 의원.")
        self.assertEqual(len([1 for k, w, _ in got if w == "곽상언 의원"]), 1)


class Verdict(unittest.TestCase):
    def test_person_thresholds(self):
        self.assertEqual(factcheck.verdict("인물", 0)[0], "??")
        self.assertEqual(factcheck.verdict("인물", 67)[0], "!!")    # 곽상원 실측값
        self.assertEqual(factcheck.verdict("인물", 459)[0], "OK")   # 곽상언 실측값

    def test_boundary(self):
        self.assertEqual(factcheck.verdict("인물", factcheck.PLENTY - 1)[0], "!!")
        self.assertEqual(factcheck.verdict("인물", factcheck.PLENTY)[0], "OK")

    def test_dates_and_numbers_never_pass_on_count(self):
        # 실측: "8월 7일"이 88만건이라 OK로 나왔지만 실제로는 틀린 날짜였다.
        # 건수로는 판정할 수 없으므로 항상 사람이 대조해야 한다.
        for kind in ("날짜", "수치"):
            self.assertEqual(factcheck.verdict(kind, 888319)[0], "??")
            self.assertEqual(factcheck.verdict(kind, 0)[0], "??")

    def test_query_failure_is_distinct(self):
        self.assertEqual(factcheck.verdict("인물", None)[0], "ER")


class NaverClean(unittest.TestCase):
    def test_strips_tags_and_entities(self):
        self.assertEqual(naver._clean("<b>곽상언</b> &quot;노무현&quot;"),
                         '곽상언 "노무현"')
        self.assertEqual(naver._clean("A &amp; B"), "A & B")

    def test_missing_keys_reported(self):
        total, msg = naver.search({}, "테스트")
        self.assertIsNone(total)
        self.assertIn("naver_client_id", msg)


if __name__ == "__main__":
    unittest.main()
