# -*- coding: utf-8 -*-
"""collect.py · factcheck.py · naver.py 단위테스트. 네트워크 없음."""
import sys
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

    def test_does_not_grab_tail_of_longer_word(self):
        # 실측: "더불어민주당"에서 "어민주당", "코인베이스"에서 "인베이스",
        # "과르디올라"에서 "르디올라"가 인물로 잡혀 !!를 남발했다
        for text, wrong in [
            ("더불어민주당 김승원 의원이 발언했다.", "어민주당"),
            ("코인베이스 부회장은 낙관했다.", "인베이스"),
            ("과르디올라 감독이 떠난 뒤", "르디올라"),
        ]:
            names = [w.split()[0] for k, w, _ in factcheck.extract(text) if k == "인물"]
            self.assertNotIn(wrong, names, text)

    def test_still_finds_real_names_in_those_sentences(self):
        names = [w for k, w, _ in factcheck.extract(
            "더불어민주당 김승원 의원이 발언했다.") if k == "인물"]
        self.assertTrue(any("김승원" in n for n in names), names)

    def test_rejects_names_ending_in_particle(self):
        # "구조는 마레스카 감독", "밀림으로 본회의장"이 인물로 잡혔다
        for text in ("빌드업 구조는 마레스카 감독의 과제다.",
                     "몸싸움과 밀림으로 본회의장이 혼란해졌다."):
            names = [w.split()[0] for k, w, _ in factcheck.extract(text) if k == "인물"]
            for junk in ("구조는", "밀림으로"):
                self.assertNotIn(junk, names, text)

    def test_keeps_names_ending_in_eun_or_i(self):
        # 은·이는 실제 이름 끝에도 온다 (한지은, 박준이)
        for name in ("한지은", "박준이"):
            names = [w.split()[0] for k, w, _ in
                     factcheck.extract(f"{name} 의원이 말했다.") if k == "인물"]
            self.assertIn(name, names)

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

    def test_dead_key_rotation_covers_revoked_and_missing_model(self):
        """폐기된 키(401)나 모델 미지원(404)에서도 다음 키로 넘어가야 한다.

        실측: 대화에 노출된 키를 폐기한 뒤 그 키가 목록 1순위에 남아 있었다.
        429만 처리하던 로직으로는 첫 호출부터 죽는다.
        """
        import inspect
        src = inspect.getsource(gemini.request)
        self.assertIn("401", src)
        self.assertIn("403", src)
        self.assertIn("404", src)
        # 다음 키로 넘어가는 분기 안에서 다뤄야 한다
        self.assertIn("dead_key", src)

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


class DailyJob(unittest.TestCase):
    """작업 스케줄러로 도는 스크립트라, 실수로 전체 실행이 시작되면 안 된다."""

    def _run(self, args):
        import contextlib
        import io
        import daily
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = daily.main(["daily.py"] + args)
        return code, buf.getvalue()

    def test_help_prints_usage_and_does_not_run(self):
        # 실측: --help가 사용법 대신 실제 실행을 시작해 API 요청을 소비했다
        code, out = self._run(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("발행은 하지 않는다", out)
        self.assertNotIn("일일 실행", out)

    def test_unknown_flag_refuses_to_run(self):
        code, out = self._run(["--nope"])
        self.assertEqual(code, 2)
        self.assertIn("모르는 옵션", out)
        self.assertNotIn("일일 실행", out)

    def test_known_flags_are_declared(self):
        import daily
        for f in ("--cats", "--publish"):
            self.assertIn(f, daily.KNOWN_FLAGS)


class SayIsCrashProof(unittest.TestCase):
    """콘솔이 없는 환경(작업 스케줄러)에서 출력 때문에 죽지 않아야 한다."""

    def test_say_survives_broken_stdout(self):
        import draft

        class Broken:
            def write(self, *a):
                raise OSError(22, "Invalid argument")

            def flush(self):
                raise OSError(22, "Invalid argument")

        old = sys.stdout
        sys.stdout = Broken()
        try:
            draft.say("아무 말")      # 예외가 새어나오면 실패
        finally:
            sys.stdout = old


class KeyTerms(unittest.TestCase):
    """핵심 용어 오타를 뉴스 건수로 잡는다.
    실측: 보완수사권 33,227건 vs 보안수사권 512건. 인물·날짜·수치가 아닌
    일반명사 오타는 다른 검사로는 잡히지 않는다."""

    TEXT = ('보안수사권 폐지 논란. 보안수사권 관련 국민의힘 반발. '
            '국민의힘 필리버스터. 필리버스터 대치. '
            '것입니다 것입니다. 개정안을 개정안을. 부회장은 부회장은.')

    def test_picks_repeated_nouns(self):
        got = factcheck.key_terms(self.TEXT)
        self.assertIn('보안수사권', got)
        self.assertIn('필리버스터', got)

    def test_drops_conjugated_and_particle_forms(self):
        # API 호출을 낭비하고 오탐을 만든다
        got = factcheck.key_terms(self.TEXT)
        for junk in ('것입니다', '개정안을', '부회장은'):
            self.assertNotIn(junk, got)

    def test_ignores_words_appearing_once(self):
        self.assertEqual(factcheck.key_terms('보완수사권 폐지 논란이 있었다.'), [])

    def test_caps_number_of_checks(self):
        many = ' '.join(f'용어{i}단어 용어{i}단어' for i in range(20))
        self.assertLessEqual(len(factcheck.key_terms(many)), factcheck.TERM_MAX_CHECKS)


if __name__ == "__main__":
    unittest.main()
