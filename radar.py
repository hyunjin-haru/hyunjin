import os
import json
import glob
import re
from datetime import datetime
from dotenv import load_dotenv

from agent import (
    search_top_youtube_videos,
    get_youtube_transcript_and_title,
    search_web_articles,
    classify_content_domain,
    save_report_to_file,
    AVAILABLE_MODELS
)
from google import genai
from notifier import send_email_alert

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

WATCHLIST_FILE = "watchlist.json"
HISTORY_FILE = "history_seen.json"

def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        default_watchlist = [
            {"keyword": "미국 기준금리 경기침체", "domain": "FINANCE_CRYPTO_MARKETS", "enabled": True},
            {"keyword": "비트코인 반감기 유동성 사이클", "domain": "FINANCE_CRYPTO_MARKETS", "enabled": True},
            {"keyword": "전고체 배터리 상용화 기술적 한계", "domain": "TECH_SCIENCE_AI", "enabled": True}
        ]
        save_watchlist(default_watchlist)
        return default_watchlist
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def harvest_and_synthesize_topic(keyword: str, domain: str = "AUTO"):
    history = load_history()
    sources = []
    harvested_urls = []
    
    print(f"\n[레이더 가동] 관심 키워드 감시 시작: '{keyword}'")
    
    try:
        yt_candidates = search_top_youtube_videos(keyword, max_count=3)
        for title, url in yt_candidates:
            if url in history:
                continue
            try:
                rtitle, transcript = get_youtube_transcript_and_title(url)
                if len(transcript) > 200:
                    sources.append((f"[유튜브 시각] {rtitle}", transcript[:3500]))
                    harvested_urls.append(url)
                    print(f"  - 유튜브 관점 수집 성공: {rtitle[:35]}...")
            except Exception:
                continue
    except Exception as e:
        print(f"  ! 유튜브 수집 에러: {e}")

    try:
        web_docs = search_web_articles(keyword, max_count=3)
        for wtitle, wtext in web_docs:
            if wtitle in history:
                continue
            sources.append((f"[원천 문서/뉴스] {wtitle}", wtext[:3500]))
            harvested_urls.append(wtitle)
            print(f"  - 웹 실증 데이터 수집 성공: {wtitle[:35]}...")
    except Exception as e:
        print(f"  ! 웹 문서 수집 에러: {e}")

    if not sources:
        print(f"  -> 새로운 정보가 없거나 수집에 실패했습니다: {keyword}")
        return None

    if domain == "AUTO" or not domain:
        sample_text = sources[0][1][:1000] if sources else ""
        try:
            domain = classify_content_domain(keyword, text_sample=sample_text)
        except Exception:
            try:
                domain = classify_content_domain(keyword, sample_text)
            except Exception:
                try:
                    domain = classify_content_domain(sample_text, keyword)
                except Exception:
                    domain = "GENERAL_KNOWLEDGE"

    combined_context = ""
    for idx, (stitle, scontent) in enumerate(sources, 1):
        combined_context += f"\n\n--- [원천 소스 {idx}: {stitle}] ---\n{scontent}"

    current_year = datetime.now().year
    synthesis_prompt = f"""
당신은 자율 지식 생태계의 수석 정보 감시관이자 제1원리 분석가입니다. 현재는 {current_year}년입니다.
아래는 수집된 서로 다른 시각과 사실을 담은 복수의 원천 소스(유튜브 영상들, 웹 뉴스, 전문 보고서)입니다.
단일 시각의 요약에 매몰되지 말고, 시각 간의 상충점을 분석하고 진짜 제약과 작동 메커니즘을 규명하는 심층 리포트를 작성하세요.

반드시 아래 마크다운 템플릿 구조를 엄격히 지켜 작성하세요:

# [{domain}] {keyword}: 다각도 교차 검증 & 제1원리 심층 리포트
> topic: "{keyword}" | domain: "{domain}" | sources_count: {len(sources)} | mode: "Autonomous Multi-Perspective Synthesis"

## 0. Executive Core Insight (다각도 종합 핵심 통찰)
- 서로 다른 시각들이 교차하는 지점에서 도출된 본질적인 1~2문장의 핵심 결론

## 1. Clash of Perspectives (쏟아지는 다양한 시각의 대립과 모순)
- 주류 해석 vs 비판적 시각 vs 현장 분석가들의 의견 차이 정리
- 어떤 정보가 과장되었고, 어떤 정보가 팩트에 기반하는지 대조

## 2. Real Constraints vs Fake Constraints (진짜 제약 vs 가짜 제약 해체)
- [가짜 제약]: 대중의 공포, 관습적 선례, 검증되지 않은 소문, 제도적 착시
- [진짜 제약]: 물리적 한계, 수학적 필연성, 자본 이동의 시차(Time-lag), 규제 및 원가 구조

## 3. Underlying Mechanics & Feedback Loops (기저 인과관계 및 작동 메커니즘)
- 표면적 사건 이면에서 실제로 돌아가는 구체적 작동 원리

## 4. Second & Third-Order Ramifications (2차·3차 파급효과 시나리오)
- 이 변화가 3~6개월 뒤 초래할 연쇄 반응

## 5. 10x Actionable Playbook (실전 대응 전략)
- 노이즈에 휩쓸리지 않고 취해야 할 10배 실행 레버리지

## 6. Structural Mindmap (통합 구조도)
```mermaid
mindmap
  root({keyword})
    핵심본질
    시각대립
    진짜제약
    작동원리
    대응전략
```

[수집된 다각도 원천 소스 모음]:
{combined_context}
"""

    print("  -> 다각도 융합 및 6-Layer 제1원리 리포트 생성 중...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    report_text = None
    for model in AVAILABLE_MODELS:
        try:
            res = client.models.generate_content(model=model, contents=synthesis_prompt)
            report_text = res.text
            break
        except Exception:
            continue

    if not report_text:
        print("  ! 리포트 생성 실패")
        return None

    saved_path = save_report_to_file(keyword, domain, report_text)
    history.extend(harvested_urls)
    save_history(history)
    print(f"  ★ [자동 채굴 성공] 리포트 저장 완료: {saved_path}")
    # 6. 스마트폰 모바일 이메일 브리핑 자동 발송
    try:
        insight_match = re.search(r'## 0\. Executive Core Insight.*?\n([\s\S]*?)(?=## 1\.)', report_text)
        insight_summary = insight_match.group(1).strip() if insight_match else report_text[:300]
        send_email_alert(f"[{domain}] {keyword} 신규 분석 보고", insight_summary)
    except Exception as e:
        print(f"  ! 알림 발송 실패: {e}")
    return saved_path

def run_radar_cycle():
    watchlist = load_watchlist()
    active_items = [item for item in watchlist if item.get("enabled", True)]
    print(f"\n==================================================")
    print(f"📡 [Second Brain 자율 감시 레이더 가동] 감시 키워드 {len(active_items)}개 순회 중...")
    print(f"==================================================")
    
    generated = []
    for item in active_items:
        kw = item.get("keyword")
        dom = item.get("domain", "AUTO")
        res = harvest_and_synthesize_topic(kw, dom)
        if res:
            generated.append(res)
            
    print(f"\n✅ 레이더 1사이클 완료: 총 {len(generated)}개의 신규 다각도 리포트 생성됨.")
    return generated

if __name__ == "__main__":
    run_radar_cycle()