# -*- coding: utf-8 -*-
"""매일 아침 자동 실행: 후보 수집 -> 카테고리별 1편 초안 -> 자동 대조.

    py -3 daily.py              6개 카테고리 각 1편
    py -3 daily.py --cats 정치 경제    지정한 카테고리만
    py -3 daily.py --publish    발행·영어판까지 (권하지 않음 — 아래 참고)

**발행은 하지 않는다.** 초안과 대조 결과만 남기고 끝낸다. 아침에 사람이
run_preview.bat 으로 읽고 publish.py --apply --en 을 돌리는 흐름이다.

발행까지 자동으로 하지 않는 이유는 실측 오류율이 편당 5건이기 때문이다. 하루 동안
잡힌 것만: 애드실드(->애드쉴드), 이산화화황(->이산화황), 곽상원(->곽상언),
파월(->케빈 워시, 현직 아님), 보안수사권(->보완수사권). 어느 것도 자동 검사만으로는
최종 판단이 되지 않았다. --publish는 그 위험을 감수하겠다고 명시할 때만 쓴다.

실행 기록은 _drafts/_daily.log 에 쌓인다. 작업 스케줄러는 콘솔이 없으므로 화면 출력에
의존하지 않는다.
"""
import datetime
import glob
import io
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARTICLES = os.path.join(ROOT, "articles")
DRAFTS = os.path.join(ROOT, "_drafts")
LOG = os.path.join(DRAFTS, "_daily.log")

RETRY_PER_VIDEO = 2       # 태그 짝 검사에 걸리는 경우가 있어 한 번은 다시 시도한다


def log(*parts):
    line = " ".join(str(p) for p in parts)
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    os.makedirs(DRAFTS, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{stamp}  {line}\n")
    try:
        print(line)
        sys.stdout.flush()
    except Exception:
        pass          # 콘솔이 없는 환경(작업 스케줄러)에서는 무시


def used_video_ids():
    """이미 기사로 만든 영상. 같은 영상을 두 번 쓰지 않는다."""
    ids = set()
    for path in glob.glob(os.path.join(ARTICLES, "*.html")) + \
            glob.glob(os.path.join(DRAFTS, "*.html")):
        try:
            with open(path, encoding="utf-8") as f:
                m = re.search(r'fs:video" content="([^"]+)', f.read())
        except Exception:
            continue
        if m:
            ids.add(m.group(1))
    return ids


def pick_one_per_category(collect, categories, used):
    """카테고리별로 가장 최근 후보 하나. 이미 쓴 영상은 건너뛴다.

    collect.py가 업로드 날짜순으로 가져오고 품질 필터를 이미 통과한 목록이므로
    맨 앞을 고르면 된다. 사람이 고를 때와 다른 점은 '판단'이 없다는 것이다 —
    필터를 통과했어도 주제가 어색한 영상이 뽑힐 수 있으니 아침 검수에서 버리면 된다.
    """
    data = collect.collect(categories)
    picked, missing = [], []
    for cat in categories:
        cand = [v for v in data.get(cat, []) if v["id"] not in used]
        if cand:
            v = cand[0]
            picked.append((cat, v))
            log(f"  [{cat}] {v['id']} {v['length']} {v['channel'][:18]} {v['title'][:44]}")
        else:
            missing.append(cat)
            log(f"  [{cat}] 쓸 만한 새 후보가 없음 — 건너뜀")
    return picked, missing


KNOWN_FLAGS = ("--cats", "--publish")


def main(argv):
    # 한글을 출력하므로 무엇보다 먼저 인코딩을 맞춘다. 이 줄이 사용법 출력보다
    # 뒤에 있어서 --help가 UnicodeEncodeError로 죽었다.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # 모르는 플래그로 실수로 전체 실행이 시작되지 않게 한다.
    # 실측에서 `--help`가 사용법 대신 실제 실행을 시작해 API 요청을 소비했다.
    flags = [a for a in argv[1:] if a.startswith("-")]
    unknown = [f for f in flags if f not in KNOWN_FLAGS]
    if unknown or "--help" in flags or "-h" in flags:
        print(__doc__)
        if unknown and "--help" not in flags and "-h" not in flags:
            print(f"모르는 옵션: {', '.join(unknown)}")
            return 2
        return 0

    sys.path.insert(0, HERE)
    import article
    import collect
    import draft
    import factcheck

    cats = argv[argv.index("--cats") + 1:] if "--cats" in argv else list(article.CATEGORIES)
    cats = [c for c in cats if not c.startswith("--")] or list(article.CATEGORIES)
    do_publish = "--publish" in argv

    log("=" * 70)
    log(f"일일 실행 {datetime.datetime.now():%Y-%m-%d %H:%M}  대상 {len(cats)}개 카테고리")

    cfg = draft.load_config()
    used = used_video_ids()
    log(f"이미 쓴 영상 {len(used)}개 제외")

    picked, missing = pick_one_per_category(collect, cats, used)
    if not picked:
        log("만들 후보가 없어 종료합니다.")
        return 1

    today = datetime.date.today().isoformat()
    made = []
    for cat, v in picked:
        url = "https://youtu.be/" + v["id"]
        for attempt in range(1, RETRY_PER_VIDEO + 1):
            r = draft.make_draft(cfg, url, today)
            if "path" in r:
                made.append(r)
                break
            log(f"  [{cat}] 실패({attempt}/{RETRY_PER_VIDEO}): {r['error']}")
        else:
            log(f"  [{cat}] 포기")

    log(f"초안 {len(made)}/{len(picked)}편 생성")
    if not made:
        return 1

    log("자동 대조 시작")
    clean, held = [], []
    for r in made:
        name = os.path.basename(r["path"])
        try:
            buf = io.StringIO()
            old, sys.stdout = sys.stdout, buf
            try:
                blockers = factcheck.check_file(cfg, r["path"], write=True) or []
            finally:
                sys.stdout = old
            hints = [l.strip() for l in buf.getvalue().split("\n")
                     if l.strip().startswith(("??", "ER"))]
            log(f"  {name}: 차단 {len(blockers)}건 / 확인권장 {len(hints)}건")
            for b in blockers:
                log(f"      ⛔ {b}")
            (held if blockers else clean).append(r)
        except Exception as e:
            log(f"  대조 실패 {name}: {e} — 안전하게 보류합니다")
            held.append(r)

    if do_publish:
        # 게이트: sanity 검사에서 '!!'가 하나라도 나온 기사는 발행하지 않고 보류한다.
        # 이 검사는 이미 교정된 기사 6편에서 오탐 0건으로 측정됐다.
        # 용어·인물 건수 검사는 같은 조건에서 '!!'를 15건 내므로 게이트로 쓰지 않는다.
        log(f"발행 대상 {len(clean)}편 / 보류 {len(held)}편")
        for r in held:
            log(f"  보류: {os.path.basename(r['path'])} — _drafts/에 남겨 둡니다")
        if clean:
            import publish
            slugs = [re.sub(r"^\d{4}-\d{2}-\d{2}-", "", os.path.splitext(
                os.path.basename(r["path"]))[0]) for r in clean]
            publish.do_publish(slugs, True, translate_too=True)
            log("발행·영어판 완료. git push는 별도로 실행됩니다.")
        else:
            log("모두 보류되어 발행하지 않았습니다.")
    else:
        log("발행은 하지 않았습니다. 아침에 확인하세요:")
        log("  run_preview.bat                     초안 읽기 (!! 항목부터)")
        log("  py -3 tools\\publish.py --apply --en  발행 + 영어판")
        log("  git push")
    if missing:
        log(f"후보가 없어 빠진 카테고리: {', '.join(missing)}")
    log("완료")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception:
        log("예외로 중단:\n" + traceback.format_exc())
        sys.exit(1)
