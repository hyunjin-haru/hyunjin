import os
import json
import re
import time
import glob
from datetime import datetime
import urllib.request
import urllib.parse
import yt_dlp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("[!] 오류: .env 파일에 GEMINI_API_KEY가 설정되지 않았습니다.")
    exit(1)

AVAILABLE_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview"
]

def clean_youtube_id(raw_id: str) -> str:
    text = str(raw_id).strip()
    match = re.search(r'([a-zA-Z0-9_-]{11})', text)
    if match:
        return match.group(1)
    return text

def search_top_youtube_videos(query: str, max_count: int = 1) -> list:
    current_year = datetime.now().year
    optimized_query = f"{query} {current_year}" if str(current_year) not in query else query
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'default_search': f'ytsearch5',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_results = ydl.extract_info(f"ytsearch5:{optimized_query}", download=False)
        entries = search_results.get('entries', [])
        
        if not entries:
            search_results = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = search_results.get('entries', [])
            
        if not entries:
            return []
            
        selected = []
        for entry in entries:
            raw_id = entry.get('id', '')
            clean_id = clean_youtube_id(raw_id)
            if not clean_id:
                continue
            video_url = f"https://www.youtube.com/watch?v={clean_id}"
            title = entry.get('title', 'Untitled')
            selected.append((title, video_url))
            if len(selected) >= max_count:
                break
                
        return selected

def get_youtube_transcript_and_title(video_url: str):
    vid = clean_youtube_id(video_url)
    clean_target_url = f"https://www.youtube.com/watch?v={vid}"

    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['ko', 'en'],
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(clean_target_url, download=False)
        video_title = info.get('title', 'Untitled_Video')
        subtitles = info.get('subtitles', {})
        auto_subtitles = info.get('automatic_captions', {})
        
        target_sub = None
        for lang in ['ko', 'en']:
            if lang in subtitles:
                target_sub = subtitles[lang]
                break
            elif lang in auto_subtitles:
                target_sub = auto_subtitles[lang]
                break
                
        if not target_sub:
            all_subs = {**subtitles, **auto_subtitles}
            if not all_subs:
                raise ValueError(f"'{video_title}' 영상에는 사용할 수 있는 자막이 없습니다.")
            target_sub = next(iter(all_subs.values()))
            
        json_sub_url = next((fmt['url'] for fmt in target_sub if fmt.get('ext') == 'json3'), None)
        
        if json_sub_url:
            req = urllib.request.Request(json_sub_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                lines = []
                for event in data.get('events', []):
                    if 'segs' in event:
                        seg_text = "".join([seg.get('utf8', '') for seg in event['segs']]).strip()
                        if seg_text and seg_text != '\n':
                            lines.append(seg_text)
                return video_title, " ".join(lines)
        else:
            first_url = target_sub[0]['url']
            req = urllib.request.Request(first_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                raw_lines = resp.read().decode('utf-8').splitlines()
                lines = [l.strip() for l in raw_lines if l.strip() and not l.startswith('WEBVTT') and not '-->' in l and not l.isdigit()]
                return video_title, " ".join(lines)

def search_web_articles(query: str, max_count: int = 2) -> list:
    encoded_query = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    )
    
    results = []
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            soup = BeautifulSoup(resp.read(), 'html.parser')
            links = soup.find_all('a', class_='result__url')
            
            target_urls = []
            for a in links:
                href = a.get('href', '')
                if 'uddg=' in href:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    actual_url = parsed.get('uddg', [None])[0]
                    if actual_url and actual_url.startswith('http'):
                        target_urls.append(actual_url)
                elif href.startswith('http'):
                    target_urls.append(href)
                if len(target_urls) >= max_count:
                    break
                    
            for target_url in target_urls:
                try:
                    page_req = urllib.request.Request(
                        target_url,
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    )
                    with urllib.request.urlopen(page_req, timeout=8) as page_resp:
                        page_soup = BeautifulSoup(page_resp.read(), 'html.parser')
                        for s in page_soup(['script', 'style', 'nav', 'header', 'footer', 'noscript']):
                            s.decompose()
                        page_title = page_soup.title.string.strip() if page_soup.title else target_url
                        paragraphs = [p.get_text().strip() for p in page_soup.find_all(['p', 'h1', 'h2', 'h3', 'article']) if len(p.get_text().strip()) > 40]
                        page_text = " ".join(paragraphs)
                        if len(page_text) > 300:
                            results.append((f"[Web] {page_title}", page_text[:4000]))
                except Exception:
                    continue
    except Exception:
        pass
        
    return results

def classify_content_domain(client: genai.Client, query_or_title: str, text_sample: str) -> str:
    prompt = (
        "아래 텍스트를 분석하여 가장 적합한 단 하나의 영문 카테고리를 선택하세요.\n\n"
        "1. TECH_HARDWARE_SYSTEMS\n"
        "2. SOFTWARE_AI_DATA\n"
        "3. FINANCE_CRYPTO_MARKETS\n"
        "4. BUSINESS_STRATEGY_OPERATIONS\n"
        "5. GEOPOLITICS_MILITARY_POLICY\n"
        "6. PHILOSOPHY_COGNITIVE_ETHICS\n"
        "7. NARRATIVE_CULTURE_MEDIA\n"
        "8. HEALTH_BIOLOGY_WELLNESS\n"
        "9. HYBRID_META_ANALYSIS\n\n"
        f"제목/주제: {query_or_title}\n"
        f"샘플 내용: {text_sample[:2000]}\n\n"
        "출력: 오직 선택된 1개의 영문 카테고리 단어만 출력하세요."
    )
    
    for model_name in AVAILABLE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            raw_cat = response.text.strip().upper()
            valid_cats = [
                "TECH_HARDWARE_SYSTEMS", "SOFTWARE_AI_DATA", "FINANCE_CRYPTO_MARKETS",
                "BUSINESS_STRATEGY_OPERATIONS", "GEOPOLITICS_MILITARY_POLICY",
                "PHILOSOPHY_COGNITIVE_ETHICS", "NARRATIVE_CULTURE_MEDIA",
                "HEALTH_BIOLOGY_WELLNESS", "HYBRID_META_ANALYSIS"
            ]
            for c in valid_cats:
                if c in raw_cat:
                    return c
            break
        except Exception:
            continue
            
    return "HYBRID_META_ANALYSIS"

def build_deep_synthesis_prompt(category: str, topic: str, sources_text: str) -> str:
    current_year = datetime.now().year
    instructions = [
        f"당신은 제1원리 기반 수석 지식 아키텍트입니다. 현재는 {current_year}년입니다.",
        f"도메인 [{category}] 시각으로 입문자부터 전문가까지 아우르는 통합 리포트를 작성하세요.",
        f"# [{topic}] 전방위 제1원리 지식 마스터 리포트",
        "",
        "## 0. Executive Core Insight (본질 관통 핵심 요약)",
        "- 이 시스템의 본질을 관통하는 단 한 문장의 통찰.",
        "",
        "## 1. Ground Zero: Foundational Axioms & Key Lexicon (기초, 기반, 핵심 어휘 사전)",
        "- 입문자도 이해할 수 있는 일상 비유와 핵심 필수 키워드 3~5개의 실질적 역할 정의.",
        "",
        "## 2. Historical Trajectory & Paradigm Shifts (역사적 배경, 변천 궤적, 현재 위치)",
        "- 과거의 출현 배경, 패러다임 전환 궤적, 현재 시점의 구조적 좌표.",
        "",
        "## 3. First Principles & Structural Mechanism (기저 메커니즘과 진짜 제약)",
        "- 물리/수학/논리적 인과관계 본질, 진짜 제약 vs 가짜 제약 해체, 교차 검증 팩트.",
        "",
        "## 4. Critical Dialectics: Pros, Cons & Counter-arguments (비판적 사고: 명과 암, 맹점과 반론)",
        "- 핵심 효용 및 기회, 구조적 취약점과 리스크, 유효한 반론(Counter-arguments).",
        "",
        "## 5. Master Playbook: Real-world Applications & Future Scenarios (실전 활용과 미래 전망)",
        "- 현업 10배 레버리지 실행 규율, 2차·3차 파급 효과와 변곡점 시나리오.",
        "",
        "## 6. Visual Mindmap & Structural Hierarchy (시각화 구조)",
        "### (A) XMind / Outliner Compatible Tree (순수 탭 들여쓰기 구조)",
        f"- {topic}",
        "\t- 1. 기초 공리 및 핵심 개념",
        "\t\t- 핵심 원리 1",
        "\t- 2. 역사적 변천과 현재 위치",
        "\t\t- 과거 배경 및 현재 국면",
        "\t- 3. 기저 메커니즘 & 진짜 제약",
        "\t\t- 작동 원리 1",
        "\t- 4. 비판적 평가 (Pros & Cons)",
        "\t\t- 장점 vs 숨은 리스크",
        "\t- 5. 실전 실행 및 미래 전망",
        "\t\t- 10x 레버리지 행동 강령",
        "",
        "### (B) Mermaid Mindmap Code Block",
        "마크다운 뷰어용 mermaid mindmap 다이어그램 코드를 작성하세요.",
        "",
        "[원천 데이터 출처 내용]",
        sources_text
    ]
    return "\n".join(instructions)

def analyze_deep_knowledge_with_gemini(topic: str, sources: list) -> tuple:
    client = genai.Client(api_key=GEMINI_API_KEY)
    combined_sources_text = ""
    for idx, (s_title, s_text) in enumerate(sources, 1):
        combined_sources_text += f"\n\n==================== [출처 {idx}: {s_title}] ====================\n{s_text}"
        
    print("  -> 콘텐츠 스캔 및 도메인 정밀 판별 중...")
    category = classify_content_domain(client, topic, combined_sources_text)
    print(f"  -> 판별 완료: [{category}] 전용 다층 심층 분석 프레임워크 가동")
    
    prompt = build_deep_synthesis_prompt(category, topic, combined_sources_text)
    
    last_error = None
    for model_name in AVAILABLE_MODELS:
        try:
            print(f"  -> [{model_name}] 모델로 기초~전문가 관통 심층 지식 합성 중...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return category, response.text
        except Exception as e:
            last_error = e
            time.sleep(1)
            
    raise last_error

def update_master_index(category: str, topic: str, file_rel_path: str, report_text: str):
    index_path = "reports/README.md"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    summary_match = re.search(r'## 0\. Executive Core Insight[^\n]*\n+([^\n#]+)', report_text)
    summary_line = summary_match.group(1).strip() if summary_match else "제1원리 심층 지식 합성 완료"
    summary_line = summary_line.replace("|", "/")[:90]
    
    file_name_only = os.path.basename(file_rel_path)
    new_entry = f"| {now_str} | `{category}` | [{topic}]({file_name_only}) | {summary_line} |\n"
    
    if not os.path.exists(index_path):
        header = """# 🧠 Autonomous Knowledge Base (Second Brain)

> 본 저장소는 제1원리(First Principles) 기반 다층 교차 검증을 거친 종합 지식 자산 카탈로그입니다.

| 생성 일시 | 도메인 | 분석 주제 (링크) | 본질 관통 핵심 인사이트 |
| :--- | :--- | :--- | :--- |
"""
        content = header + new_entry
    else:
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        content += new_entry

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)

def save_report_to_file(title: str, category: str, report: str) -> str:
    os.makedirs("reports", exist_ok=True)
    clean_title = re.sub(r'[\\/*?:"<>|]', "", title)[:40].strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reports/[{category}]_{clean_title}_{timestamp}.md"
    
    meta_header = f"""---
topic: "{title}"
domain: "{category}"
generated_at: "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
mode: "Full-Spectrum First Principles Synthesis"
tags:
  - First-Principles
  - Deep-Knowledge
  - Cross-Verification
  - {category}
---

"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(meta_header + report)
        
    update_master_index(category, title, filename, report)
    return filename

def execute_discovery_pipeline(user_input: str):
    """지정된 주제에 대해 유튜브와 웹을 자율 스크래핑하고 리포트를 생성하는 독립 실행 파이프라인"""
    sources = []
    if user_input.startswith("http://") or user_input.startswith("https://"):
        print(f"\n[1/3] 단일 URL 모드: 원천 데이터 추출 중...")
        try:
            t, txt = get_youtube_transcript_and_title(user_input)
            sources.append((t, txt))
            topic_name = t
            print(f"  -> 수집 완료: {t} ({len(txt):,}자)")
        except Exception as e:
            print(f"[!] 추출 실패: {e}")
            return None
    else:
        print(f"\n[1/3] 복합 원천(영상 + 웹) 동시 자율 탐색: '{user_input}'...")
        topic_name = user_input
        try:
            yt_targets = search_top_youtube_videos(user_input, max_count=1)
            for t, u in yt_targets:
                print(f"  [유튜브 탐색] {t}")
                try:
                    real_title, raw_txt = get_youtube_transcript_and_title(u)
                    sources.append((f"[YouTube] {real_title}", raw_txt))
                    print(f"      -> 자막 추출 완료 ({len(raw_txt):,}자)")
                except Exception as ex:
                    print(f"      -> [스킵] 자막 미지원: {ex}")
        except Exception as e:
            print(f"  [!] 영상 탐색 지연: {e}")
            
        print(f"  [웹 원천 탐색] 관련 학술·정책·기술 분석 아티클 수집 중...")
        try:
            web_results = search_web_articles(user_input, max_count=2)
            for wt, wtxt in web_results:
                sources.append((wt, wtxt))
                print(f"      -> 문서 추출 완료: {wt[:45]}... ({len(wtxt):,}자)")
        except Exception as e:
            print(f"  [!] 웹 탐색 지연: {e}")
            
        if not sources:
            print("[!] 분석 가능한 원천 데이터를 확보하지 못했습니다.")
            return None
            
    print(f"\n[2/3] 도메인 라우팅 및 6단계 전방위 제1원리 심층 지식 합성 수행...")
    try:
        category, report = analyze_deep_knowledge_with_gemini(topic_name, sources)
        print(f"\n[3/3] 심층 리포트 저장 및 마스터 인덱스 갱신...")
        saved_path = save_report_to_file(topic_name, category, report)
        print(f"  -> 저장 완료: {saved_path}")
        print(f"  -> 마스터 인덱스: reports/README.md 업데이트 완료")
        return saved_path
    except Exception as e:
        print(f"\n[!] 오류 발생: {e}")
        return None

def run_interactive_second_brain():
    report_files = glob.glob("reports/*.md")
    report_files = [f for f in report_files if not f.endswith("README.md")]
    
    if not report_files:
        print("\n[!] reports/ 폴더에 축적된 리포트가 없습니다. 먼저 1번 모드로 지식을 발굴하세요.")
        return
        
    print(f"\n[세컨드 브레인 활성화] 총 {len(report_files)}개의 지식 문서를 메모리에 로드했습니다.")
    print("💡 꼬리 질문과 심층 토론이 가능합니다. (종료하려면 'q' 또는 'exit' 입력)")
    print("-" * 70)
    
    knowledge_context = ""
    for fpath in report_files:
        fname = os.path.basename(fpath)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
            knowledge_context += f"\n\n==================== [지식 문서: {fname}] ====================\n{content[:4000]}"
            
    client = genai.Client(api_key=GEMINI_API_KEY)
    chat_history = []
    
    while True:
        user_query = input("\n[질문 / 꼬리질문]: ").strip()
        if not user_query:
            continue
        if user_query.lower() in ['q', 'exit', 'quit', '종료']:
            print("세컨드 브레인 질의 세션을 종료합니다.\n")
            break
            
        history_text = ""
        if chat_history:
            history_text = "\n[이전 대화 맥락]:\n"
            for q, a in chat_history[-3:]:
                history_text += f"Q: {q}\nA: {a}\n---\n"
                
        prompt = f"""
당신은 사용자의 전용 Second Brain 수석 아키텍트입니다.
사용자의 질문과 이전 대화 맥락을 참조하고, 아래 지식 문서들의 내용을 엄밀하게 교차 참조하여 답변하세요.

[축적된 지식 베이스 문서 내용]:
{knowledge_context}
{history_text}
[사용자의 현재 질문]: {user_query}

[답변 작성 수칙]:
1. 제1원리 관점에서 직설적이고 명쾌하게 결론부터 제시하세요.
2. 답변에 활용된 핵심 논리와 팩트가 어떤 [지식 문서 파일명]에서 비롯되었는지 명시하세요.
3. 이전 대화 맥락이 있다면 자연스럽게 꼬리 질문을 이어받아 답변의 깊이를 한 층 더 심화하세요.
4. 축적된 문서만으로 답하기 부족한 부분은 솔직하게 짚어내세요.
"""
        print("  -> 내 지식 창고 기반 교차 추론 및 답변 합성 중...")
        answered = False
        for model_name in AVAILABLE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                answer_text = response.text
                print("\n" + "=" * 70)
                print("  🧠 Second Brain Insight:")
                print("=" * 70)
                print(answer_text)
                print("=" * 70)
                
                chat_history.append((user_query, answer_text[:500] + "..."))
                answered = True
                break
            except Exception:
                continue
                
        if not answered:
            print("[!] 답변 생성 중 오류가 발생했습니다. 다시 시도해 주세요.")

def run_cross_synthesis_mode():
    report_files = sorted(glob.glob("reports/*.md"))
    report_files = [f for f in report_files if not f.endswith("README.md")]
    
    if len(report_files) < 2:
        print("\n[!] 교차 융합을 진행하려면 최소 2개 이상의 리포트가 필요합니다.")
        return
        
    print("\n" + "=" * 70)
    print("  [보관된 지식 리포트 목록]")
    print("=" * 70)
    for idx, fpath in enumerate(report_files, 1):
        fname = os.path.basename(fpath)
        print(f"  [{idx}] {fname}")
    print("=" * 70)
    
    selected_input = input("\n융합할 리포트 번호를 2개 이상 입력하세요 (예: 1, 2): ").strip()
    if not selected_input:
        return
        
    try:
        chosen_indices = [int(x.strip()) - 1 for x in selected_input.split(",") if x.strip().isdigit()]
        chosen_indices = list(set([i for i in chosen_indices if 0 <= i < len(report_files)]))
        if len(chosen_indices) < 2:
            print("[!] 유효한 번호를 2개 이상 선택해야 합니다.")
            return
    except Exception:
        print("[!] 번호 입력 형식이 올바르지 않습니다.")
        return
        
    selected_files = [report_files[i] for i in chosen_indices]
    combined_docs = ""
    topic_titles = []
    
    for fpath in selected_files:
        fname = os.path.basename(fpath)
        topic_titles.append(fname.split("_")[1] if "_" in fname else fname)
        with open(fpath, "r", encoding="utf-8") as f:
            combined_docs += f"\n\n==================== [지식 문서: {fname}] ====================\n{f.read()}"
            
    meta_topic = " & ".join(topic_titles[:3])
    print(f"\n[지식 융합 가동] 대상: '{meta_topic}'...")
    
    current_year = datetime.now().year
    prompt = f"""
당신은 제1원리 기반의 거시 지식 합성(Meta-Synthesis) 수석 아키텍트입니다. 현재는 {current_year}년입니다.
아래 복수의 독립된 지식 리포트들을 심층 결합하여 구조적 상호작용과 거대한 메타 통찰 리포트를 작성하세요.

# [{meta_topic}] 지식 융합 & 상호작용 메타 리포트

## 0. Executive Core Insight (융합 핵심 통찰)
## 1. Interconnected Mechanics (상호 인과 메커니즘 및 피드백 루프)
## 2. Clash of Constraints: Real vs Fake (제약의 충돌과 상충관계)
## 3. Second-Order & Third-Order Systemic Effects (2차·3차 거시 파급 효과)
## 4. Unified 10x Strategic Playbook (통합 10배 실행 레버리지)
## 5. Visual Mindmap & Structural Hierarchy (통합 마인드맵: 순수 탭 들여쓰기 트리 + mermaid mindmap 코드)

[결합할 원천 지식 리포트 내용]:
{combined_docs}
"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    for model_name in AVAILABLE_MODELS:
        try:
            print(f"  -> [{model_name}] 모델로 메타 융합 리포트 합성 중...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            report_text = response.text
            saved_path = save_report_to_file(f"융합_{meta_topic}", "META_SYNTHESIS", report_text)
            
            print("\n" + "=" * 70)
            print("  🧬 Meta-Synthesis Report Generated:")
            print("=" * 70)
            print(report_text)
            print("=" * 70)
            print(f"\n[성공] 지식 융합 완료: {saved_path}")
            return
        except Exception:
            continue
            
    print("[!] 메타 리포트 생성 중 오류가 발생했습니다.")

def run_knowledge_audit_mode():
    report_files = sorted(glob.glob("reports/*.md"))
    report_files = [f for f in report_files if not f.endswith("README.md")]
    
    if not report_files:
        print("\n[!] 감사할 지식 리포트가 없습니다. 먼저 1번 모드로 지식을 채굴하세요.")
        return
        
    print(f"\n[지식 감사관 가동] 보관된 총 {len(report_files)}개의 리포트 스트레스 테스트 시작...")
    
    all_knowledge_summary = ""
    for idx, fpath in enumerate(report_files, 1):
        fname = os.path.basename(fpath)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
            all_knowledge_summary += f"\n\n--- [문서 {idx}: {fname}] ---\n{content[:2500]}"
            
    current_year = datetime.now().year
    prompt = f"""
당신은 제1원리 기반의 냉혹하고 비판적인 '수석 지식 감사관(Chief Knowledge Auditor)'입니다. 현재는 {current_year}년입니다.
아래 Second Brain에 보관된 지식 리포트들을 전수 분석하여 신뢰성을 극대화하기 위한 정밀 감사 보고서를 작성하세요.

# 🛡️ Second Brain 지식 스트레스 테스트 & 공백 감사 보고서

## 1. Contradictions & Temporal Conflicts (모순 및 시계열 충돌 감지)
- 서로 다른 리포트 간에 데이터, 전제, 결론이 충돌하거나 시계열적으로 어긋나는 지점 적시.

## 2. Fragile Assumptions & Unproven Beliefs (취약한 가정과 가짜 제약 감사)
- 증명 없이 무비판적으로 수용하고 있는 도그마, 사회적 관습, 시장의 유행(Hype) 해체.

## 3. Critical Knowledge Gaps (치명적 지식 공백 및 사각지대)
- 지식 네트워크를 완결하기 위해 누락된 결정적 연결고리 규명.

## 4. Next Research Quests (다음 채굴 우선순위 키워드 추천)
- 모순을 해결하고 공백을 메우기 위해 즉시 탐색해야 할 핵심 키워드 3가지를 반드시 아래 형식으로 출력하세요:
  1. [키워드1] - (추천 이유)
  2. [키워드2] - (추천 이유)
  3. [키워드3] - (추천 이유)

[감사 대상 지식 베이스 요약]:
{all_knowledge_summary}
"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("  -> 문서 간 정합성 검증 및 논리적 결함 스트레스 테스트 중...")
    
    for model_name in AVAILABLE_MODELS:
        try:
            print(f"  -> [{model_name}] 모델로 비판적 지식 감사 진행 중...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            report_text = response.text
            saved_path = save_report_to_file("지식_감사_스트레스테스트", "AUDIT_REPORT", report_text)
            
            print("\n" + "=" * 70)
            print("  🛡️ Knowledge Stress-Test & Gap Audit Result:")
            print("=" * 70)
            print(report_text)
            print("=" * 70)
            print(f"\n[성공] 감사 완료: {saved_path}")
            
            # --- 자율 채굴 순환 루프 (Self-Healing Loop) ---
            keywords = re.findall(r'\[(.*?)\]', report_text)
            # 유효 키워드 필터링
            keywords = [k for k in keywords if len(k) > 1 and "키워드" not in k][:3]
            
            if keywords:
                print("\n" + "-" * 70)
                print("🔄 [자율 순환 루프] 감사관이 지식 공백을 메울 다음 탐색 키워드를 감지했습니다:")
                for i, kw in enumerate(keywords, 1):
                    print(f"  [{i}] {kw}")
                print("  [0] 채굴 건너뛰기 (메인 메뉴 복귀)")
                print("-" * 70)
                
                auto_pick = input("즉시 자율 채굴하여 공백을 메울 번호를 선택하세요 (1~3 또는 0): ").strip()
                if auto_pick in ["1", "2", "3"]:
                    target_kw = keywords[int(auto_pick) - 1]
                    print(f"\n🚀 [자동 채굴 가동] '{target_kw}'에 대한 자율 조사를 즉시 시작합니다...")
                    execute_discovery_pipeline(target_kw)
            return
        except Exception:
            continue
            
    print("[!] 지식 감사 진행 중 오류가 발생했습니다.")

def run_discovery_mode():
    user_input = input("\n[입력] 탐색하고 싶은 전문 주제/키워드 또는 영상 URL을 입력하세요: ").strip()
    if not user_input:
        return
    execute_discovery_pipeline(user_input)

if __name__ == "__main__":
    while True:
        print("=" * 70)
        print("  Autonomous Knowledge Synthesizer & Second Brain Engine")
        print("=" * 70)
        print("  [1] 신규 지식 자율 발굴 및 심층 리포트 생성 (Discovery Mode)")
        print("  [2] 내 세컨드 브레인과 연속 대화하기 (Interactive Brain Chat)")
        print("  [3] 지식 간 교차 융합 메타 리포트 생성 (Cross-Report Synthesis)")
        print("  [4] 내 지식 베이스 스트레스 테스트 및 공백 진단 (Audit Mode)")
        print("  [0] 프로그램 종료 (Exit)")
        print("=" * 70)
        
        choice = input("\n실행할 메뉴 번호를 선택하세요 (1, 2, 3, 4, 0): ").strip()
        
        if choice == "1":
            run_discovery_mode()
        elif choice == "2":
            run_interactive_second_brain()
        elif choice == "3":
            run_cross_synthesis_mode()
        elif choice == "4":
            run_knowledge_audit_mode()
        elif choice == "0":
            print("\n프로그램을 종료합니다.")
            break
        else:
            print("올바른 번호를 선택해 주세요.")