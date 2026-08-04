# -*- coding: utf-8 -*-
"""collect.py · factcheck.py · naver.py 단위테스트. 네트워크 없음."""
import unittest

import collect
import factcheck
import gemini
import gnews
import naver
import wiki


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

    def test_drops_english_clickbait(self):
        # 실측: "TOP Economist ISSUES URGENT RECESSION WARNING"이 한국어 필터를 통과했다
        for bad in ("🚨TOP Economist ISSUES URGENT RECESSION WARNING",
                    "BITCOIN PRICE PREDICTION 2026",
                    "THIS CHANGES EVERYTHING FOR THE USD MARKET NOW",
                    "Is this a SCAM? What the data says",
                    "You won't believe what happened next"):
            self.assertFalse(collect.keep(video(title=bad, channel="BBC"), False), bad)

    def test_keeps_legitimate_english_title(self):
        # 약어(FOMC·ECB·BOJ)는 대문자 연속 필터에 걸리지 않아야 한다
        for good in ("Global Economy & Markets: Why the Rally May Continue",
                     "FOMC holds rates: what the ECB does next",
                     "How the ECB and BOJ diverged in 2026",
                     "Premier League tactical analysis: Arsenal build-up"):
            self.assertTrue(collect.keep(video(title=good, channel="BBC"), False), good)

    def test_english_queries_only_for_relevant_categories(self):
        # 정치는 국내 사안이라 영어 검색어를 쓰지 않는다 (해외 정치는 '세계'로 분류)
        self.assertNotIn("정치", collect.EN_QUERIES)
        for cat in ("경제", "암호화폐", "스포츠", "세계", "스타트업"):
            self.assertTrue(collect.EN_QUERIES.get(cat), cat)

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
        # 인물은 위키백과로 따로 확인하므로 (이름, 직함) 튜플을 들고 간다
        got = factcheck.extract("곽상언 의원만이 유일하게 반대표를 던졌다.")
        self.assertIn(("인물", "곽상언 의원", ("곽상언", "의원")), got)

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


class WikiTitleMatch(unittest.TestCase):
    """기사가 쓴 직함이 위키백과 첫 문단에 있는지. 판정이 아니라 힌트다."""

    WARSH = ("케빈 맥스웰 워시는 미국의 금융인으로, 2026년부터 미국 중앙은행 "
             "연방준비제도 의장을 맡고 있다.")
    KWAK = ("곽상언은 대한민국의 법조인, 정치인이며, 제22대 국회의원이다. "
            "노무현 대한민국 제16대 대통령의 사위이다.")

    def test_matches_abbreviated_title(self):
        # 기사는 "연준 의장"으로 줄여 쓰지만 위키백과는 "연방준비제도 의장"이다
        self.assertTrue(wiki.title_matches(self.WARSH, "연준 의장"))
        self.assertTrue(wiki.title_matches(self.KWAK, "의원"))

    def test_detects_wrong_title(self):
        self.assertFalse(wiki.title_matches(self.KWAK, "교수"))
        self.assertFalse(wiki.title_matches(self.WARSH, "총리"))

    def test_handles_org_prefixed_title(self):
        self.assertTrue(wiki.title_matches(self.WARSH, "연방준비제도 의장"))

    def test_empty_inputs(self):
        self.assertFalse(wiki.title_matches("", "의원"))
        self.assertFalse(wiki.title_matches(self.KWAK, ""))


class GnewsParse(unittest.TestCase):
    def test_clean_strips_tags_and_entities(self):
        self.assertEqual(gnews._clean("<b>Fed</b> &amp; ECB"), "Fed & ECB")

    def test_known_locales(self):
        for lang in ("en", "ko"):
            self.assertIn("hl", gnews.LOCALES[lang])

    def test_unknown_lang_falls_back_to_english(self):
        # search()가 알 수 없는 언어를 받아도 죽지 않아야 한다
        self.assertEqual(gnews.LOCALES.get("zz", gnews.LOCALES["en"]),
                         gnews.LOCALES["en"])


class GeminiKeys(unittest.TestCase):
    """무료 티어의 병목은 토큰이 아니라 요청 횟수(하루 20회)다.
    키는 발급이 무료이고 한도가 키마다 별도라 여러 개를 순환한다."""

    def test_single_key(self):
        self.assertEqual(gemini.api_keys({"gemini_api_key": "A"}), ["A"])

    def test_list_plus_single_without_duplicates(self):
        self.assertEqual(
            gemini.api_keys({"gemini_api_keys": ["A", "B"], "gemini_api_key": "A"}),
            ["A", "B"])
        self.assertEqual(
            gemini.api_keys({"gemini_api_keys": ["A"], "gemini_api_key": "B"}),
            ["A", "B"])

    def test_string_instead_of_list(self):
        self.assertEqual(gemini.api_keys({"gemini_api_keys": "A"}), ["A"])

    def test_no_key_raises(self):
        with self.assertRaises(RuntimeError):
            gemini.api_keys({})

    def test_daily_quota_vs_rate_limit(self):
        # 하루 한도는 기다려도 안 풀리므로 다음 키로 넘어가야 하고,
        # 분당 한도는 기다리면 풀리므로 재시도해야 한다
        self.assertTrue(gemini.is_daily_quota(
            "Quota exceeded for metric: generate_content_free_tier_requests, limit: 20"))
        self.assertTrue(gemini.is_daily_quota("GenerateRequestsPerDayPerProject"))
        self.assertFalse(gemini.is_daily_quota("GenerateRequestsPerMinute"))


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
