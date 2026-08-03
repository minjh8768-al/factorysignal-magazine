# -*- coding: utf-8 -*-
"""유튜브 메타데이터 조회.

출처 표기는 LLM에게 맡기지 않는다. 실측에서 Gemini가 채널·프로그램명과 연도를
지어냈다(2026년 영상을 "2022.07.31"로 표기). oEmbed는 API 키 없이 실제 값을 준다.
"""
import json
import urllib.request

OEMBED = "https://www.youtube.com/oembed?url={url}&format=json"


def fetch_meta(video_id, timeout=20):
    """{'channel': ..., 'title': ...} 를 반환한다."""
    watch = f"https://www.youtube.com/watch?v={video_id}"
    with urllib.request.urlopen(OEMBED.format(url=watch), timeout=timeout) as resp:
        data = json.load(resp)
    channel = (data.get("author_name") or "").strip()
    title = (data.get("title") or "").strip()
    if not title:
        raise RuntimeError(f"영상 제목을 가져올 수 없습니다: {video_id}")
    return {"channel": channel, "title": title}


def source_title(meta):
    """출처 표기 한 줄. 예: 'SBS 뉴스 · [정치사냥꾼] ...'"""
    if meta["channel"]:
        return f"{meta['channel']} · {meta['title']}"
    return meta["title"]
