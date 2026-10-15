import os
import glob
import re
import json
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

# 백엔드 엔진 핵심 함수 임포트
from agent import (
    search_top_youtube_videos,
    get_youtube_transcript_and_title,
    search_web_articles,
    classify_content_domain,
    analyze_deep_knowledge_with_gemini,
    save_report_to_file,
    AVAILABLE_MODELS
)
from radar import (
    load_watchlist,
    save_watchlist,
    run_radar_cycle,
    harvest_and_synthesize_topic
)
from google import genai

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

st.set_page_config(
    page_title="Second Brain OS",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- 유틸리티: Mermaid 그래픽 렌더러 (에러 방어형) -----------------
def clean_mermaid_code(code: str) -> str:
    """Mermaid 문법 충돌을 방지하기 위해 특수문자 및 기호를 정돈합니다."""
    clean = code.strip().replace("```mermaid", "").replace("```", "").strip()
    lines = clean.splitlines()
    processed_lines = []
    
    for line in lines:
        if not line.strip():
            continue
        if line.strip().startswith("mindmap") or line.strip().startswith("graph") or line.strip().startswith("flowchart"):
            processed_lines.append(line)
            continue
        
        indent = len(line) - len(line.lstrip())
        content = line.strip()
        
        if content.startswith("- ") or content.startswith("* "):
            content = content[2:].strip()
            
        safe_content = re.sub(r'[\(\)\[\]\{\}\"\':;]', ' ', content).strip()
        safe_content = re.sub(r'\s+', ' ', safe_content)
        
        if safe_content:
            processed_lines.append(" " * max(2, indent) + safe_content)
            
    return "\n".join(processed_lines)

def render_mermaid(code: str, height: int = 420):
    """Mermaid 자바스크립트 엔진으로 다이어그램을 브라우저에 렌더링합니다."""
    safe_code = clean_mermaid_code(code)
    html_code = f"""
    <div id="mermaid-container" style="display: flex; justify-content: center; align-items: center; background: #0e1117; border-radius: 8px; padding: 15px; min-height: 250px;">
        <pre class="mermaid" style="background: transparent;">
{safe_code}
        </pre>
    </div>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            securityLevel: 'loose'
        }});
    </script>
    """
    components.html(html_code, height=height, scrolling=True)

def load_all_reports():
    """reports 디렉터리의 마크다운 리포트 목록을 반환합니다."""
    files = sorted(glob.glob("reports/*.md"), reverse=True)
    return [f for f in files if not f.endswith("README.md")]

# ----------------- 사이드바: 지식 아카이브 -----------------
with st.sidebar:
    st.title("🧠 Second Brain")
    st.caption("제1원리 기반 자율 지식 생태계")
    st.markdown("---")
    
    reports = load_all_reports()
    st.subheader(f"📚 지식 창고 ({len(reports)}개)")
    
    selected_report_file = None
    if reports:
        report_names = [os.path.basename(f) for f in reports]
        selected_name = st.selectbox("리포트 열람 선택", report_names)
        selected_report_file = os.path.join("reports", selected_name)
    else:
        st.info("저장된 리포트가 없습니다.")
        
    st.markdown("---")
    if os.path.exists("reports/README.md"):
        with open("reports/README.md", "r", encoding="utf-8") as f:
            st.download_button(
                label="📥 마스터 카탈로그(README) 다운로드",
                data=f.read(),
                file_name="README.md",
                mime="text/markdown"
            )

# ----------------- 메인 인터페이스 탭 분리 -----------------
tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📡 자율 레이더 관제실 (Radar)",
    "🔍 수동 지식 채굴 (Discovery)",
    "💬 세컨드 브레인 대화 (Chat)",
    "🧬 메타 교차 융합 (Cross-Synthesis)",
    "🛡️ 지식 스트레스 감사 (Audit)",
    "📖 리포트 열람실 & 마인드맵 (Reader)"
])

# ----------------- TAB 0: Autonomous Radar Control -----------------
with tab0:
    st.header("📡 자율 관심사 레이더 관제실 (Autonomous Radar)")
    st.caption("내가 직접 찾아보지 않아도, 백그라운드 레이더가 다양한 시각(유튜브 다수 + 웹 뉴스/학술 문서)을 스스로 감시하고 분석하여 지식 창고에 적재합니다.")
    
    col_rad1, col_rad2 = st.columns([3, 1])
    with col_rad1:
        st.subheader("🎯 감시 키워드 관리 (Watchlist)")
    with col_rad2:
        if st.button("⚡ 지금 전체 레이더 1회 즉시 가동", use_container_width=True):
            with st.status("자율 레이더 순회 채굴 중...", expanded=True) as status:
                st.write("등록된 관심 키워드들을 순회하며 다각도 시각을 탐색합니다...")
                generated = run_radar_cycle()
                if generated:
                    status.update(label=f"레이더 순회 완료! {len(generated)}개 신규 리포트 생성됨", state="complete")
                    st.success(f"새로운 리포트 {len(generated)}개가 지식 창고에 자동 편입되었습니다.")
                    st.rerun()
                else:
                    status.update(label="새로운 정보가 없거나 이미 수집 완료되었습니다.", state="complete")
                    st.info("모든 키워드가 최신 상태입니다. 새로운 이슈가 감지되면 자동으로 생성됩니다.")

    watchlist = load_watchlist()
    
    # 1. 새 키워드 추가 폼
    with st.expander("➕ 새로운 관심 키워드 등록", expanded=False):
        c_kw, c_dom = st.columns([3, 1])
        with c_kw:
            new_kw = st.text_input("감시할 주제 / 키워드", placeholder="예: 전고체 배터리 양산 수율, 엔비디아 차세대 아키텍처")
        with c_dom:
            new_dom = st.selectbox("도메인", ["AUTO", "FINANCE_CRYPTO_MARKETS", "TECH_SCIENCE_AI", "GEOPOLITICS_MILITARY", "NARRATIVE_CULTURE_MEDIA"])
        
        if st.button("등록하기"):
            if new_kw.strip():
                watchlist.append({"keyword": new_kw.strip(), "domain": new_dom, "enabled": True})
                save_watchlist(watchlist)
                st.success(f"'{new_kw}' 감시 목록에 등록되었습니다!")
                st.rerun()

    # 2. 등록된 키워드 목록 테이블 및 토글
    st.write("---")
    if watchlist:
        for idx, item in enumerate(watchlist):
            c_chk, c_txt, c_badge, c_del = st.columns([0.5, 4, 2, 1])
            with c_chk:
                is_active = st.checkbox("", value=item.get("enabled", True), key=f"chk_{idx}")
                if is_active != item.get("enabled", True):
                    watchlist[idx]["enabled"] = is_active
                    save_watchlist(watchlist)
                    st.rerun()
            with c_txt:
                st.write(f"**{item.get('keyword')}**")
            with c_badge:
                st.caption(f"🏷️ {item.get('domain', 'AUTO')}")
            with c_del:
                if st.button("삭제", key=f"del_{idx}"):
                    watchlist.pop(idx)
                    save_watchlist(watchlist)
                    st.rerun()
    else:
        st.info("등록된 감시 키워드가 없습니다. 위에서 새 키워드를 등록하세요.")

    # 3. 레이더 자동 채굴 결과 피드
    st.write("---")
    st.subheader("📰 최근 자율 채굴된 인사이트 피드")
    auto_reports = [f for f in load_all_reports() if not "융합_" in f and not "감사_" in f]
    if auto_reports:
        for rf in auto_reports[:5]:
            fname = os.path.basename(rf)
            with open(rf, "r", encoding="utf-8") as f:
                head_text = f.read()[:1500]
            with st.container():
                st.markdown(f"#### 📄 {fname}")
                # Executive Core Insight 추출
                insight_match = re.search(r'## 0\. Executive Core Insight.*?\n([\s\S]*?)(?=## 1\.)', head_text)
                if insight_match:
                    st.info(insight_match.group(1).strip())
                else:
                    st.write(head_text[:250] + "...")
                st.markdown("---")
    else:
        st.caption("아직 자동 채굴된 리포트가 없습니다.")

# ----------------- TAB 1: Discovery Mode -----------------
with tab1:
    st.header("수동 원포인트 지식 채굴 및 6-Layer 심층 합성")
    st.caption("특정 URL이나 단발성 궁금증을 직접 입력하여 즉시 채굴하고 분석합니다.")
    
    col1, col2 = st.columns([4, 1])
    with col1:
        query_input = st.text_input("탐색할 전문 키워드 또는 특정 유튜브 영상 URL", placeholder="예: 양자 컴퓨팅, 전고체 배터리, 사주팔자 천문학적 기원")
    with col2:
        st.write("")
        st.write("")
        discover_btn = st.button("🚀 즉시 채굴 시작", use_container_width=True)
        
    if discover_btn and query_input.strip():
        with st.status("지식 채굴 및 합성 파이프라인 가동 중...", expanded=True) as status:
            sources = []
            topic_name = query_input.strip()
            
            if topic_name.startswith("http://") or topic_name.startswith("https://"):
                st.write("단일 영상 모드: 자막 데이터 추출 중...")
                t, txt = get_youtube_transcript_and_title(topic_name)
                sources.append((t, txt))
                topic_name = t
            else:
                st.write(f"최신성 기반 유튜브 탐색 중: '{topic_name}'...")
                yt_targets = search_top_youtube_videos(topic_name, max_count=1)
                for t, u in yt_targets:
                    try:
                        rt, rtxt = get_youtube_transcript_and_title(u)
                        sources.append((f"[YouTube] {rt}", rtxt))
                        st.write(f"  -> 영상 확보: {rt[:40]}...")
                    except Exception:
                        pass
                
                st.write("웹/학술 원천 아티클 동시 수집 중...")
                web_results = search_web_articles(topic_name, max_count=2)
                for wt, wtxt in web_results:
                    sources.append((wt, wtxt))
                    st.write(f"  -> 웹 문서 확보: {wt[:40]}...")
            
            if not sources:
                status.update(label="원천 데이터를 확보하지 못했습니다.", state="error")
            else:
                st.write("도메인 라우팅 및 6-Layer 제1원리 합성 중...")
                category, report_text = analyze_deep_knowledge_with_gemini(topic_name, sources)
                saved_path = save_report_to_file(topic_name, category, report_text)
                status.update(label=f"합성 완료! '{saved_path}' 저장됨", state="complete")
                
                st.success(f"[{category}] 도메인으로 합성 완료!")
                
                mermaid_blocks = re.findall(r'```mermaid([\s\S]*?)```', report_text)
                if mermaid_blocks:
                    st.subheader("🗺️ 지식 구조 마인드맵 (그래픽 차트)")
                    for mb in mermaid_blocks:
                        render_mermaid(mb)
                st.markdown(report_text)

# ----------------- TAB 2: Interactive Chat -----------------
with tab2:
    st.header("내 세컨드 브레인과 심층 질의응답 (Deep Thought RAG)")
    st.caption("내 지식 문서를 출발점으로 삼고, 기저 원리와 2차 인과관계까지 거침없이 파고듭니다.")
    
    col_opt1, col_opt2 = st.columns([1, 1])
    with col_opt1:
        reasoning_mode = st.radio(
            "사고 모드 선택",
            ["🚀 제1원리 심층 확장 모드 (추천: 내 문서 + 심층 논리/메커니즘 규명)", "🔒 엄격한 문서 고정 모드 (오직 내 문서 내용만 요약)"],
            index=0
        )
    with col_opt2:
        st.write("")
        if st.button("🗑️ 대화 기록 초기화"):
            st.session_state.chat_messages = []
            st.rerun()

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if user_prompt := st.chat_input("꼬리 질문을 던지거나 더 깊이 알고 싶은 메커니즘을 물어보세요..."):
        st.session_state.chat_messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)
            
        reports = load_all_reports()
        if not reports:
            with st.chat_message("assistant"):
                st.warning("아직 축적된 지식 문서가 없습니다. 먼저 1번 탭에서 지식을 채굴하세요.")
        else:
            knowledge_context = ""
            for fpath in reports:
                fname = os.path.basename(fpath)
                with open(fpath, "r", encoding="utf-8") as f:
                    knowledge_context += f"\n\n==================== [문서: {fname}] ====================\n{f.read()[:3500]}"
            
            history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state.chat_messages[-4:]])
            
            if "심층 확장" in reasoning_mode:
                prompt_instruction = """
[임무 지침 - 제1원리 심층 확장 모드]:
1. 지식 베이스의 문서를 '한계'가 아닌 '도약대(출발점)'로 활용하세요.
2. 문서에 직접 적혀 있지 않은 내용이라도, 기저에 깔린 수학적 필연성, 물리 법칙, 시장 메커니즘, 기술적 인과관계를 최상위 수준의 전문 지식으로 확장해 끝까지 파고들어 설명하세요.
3. 피상적이거나 두루뭉술한 조언을 배제하고, 구체적인 작동 원리를 논리적으로 증명하듯 전개하세요.
4. 반드시 다음 3단계 구조로 답변하세요:
   - 📌 [내 지식 베이스의 연결점]: 질문과 관련된 보관 문서의 핵심 전제/데이터 명시
   - 🔬 [기저 메커니즘 심층 해부]: 1단계에서 더 나아가 작동하는 진짜 이유와 구체적 메커니즘 (전문적 수준)
   - 💡 [2차 파급효과 및 실전 맹점]: 현업이나 실전에서 놓치기 쉬운 가짜 제약 해체 및 결론
"""
            else:
                prompt_instruction = """
[임무 지침 - 엄격한 문서 고정 모드]:
1. 오직 아래 축적된 지식 베이스 문서에 명시된 사실과 내용만 사용하여 답변하세요.
2. 문서에 없는 내용은 추측하지 말고 솔직하게 지식 베이스에 없다고 밝히세요.
"""

            prompt = f"""
당신은 사용자의 전용 Second Brain 수석 아키텍트이자 제1원리 분석관입니다.
사용자의 질문과 이전 대화 맥락을 파악하고 답변하세요.

{prompt_instruction}

[축적된 지식 베이스 문서]:
{knowledge_context}

[이전 대화 이력]:
{history_text}

[사용자의 질문]: {user_prompt}
"""
            with st.chat_message("assistant"):
                with st.spinner("지식 확장 및 심층 인과관계 추론 중..."):
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    answered = False
                    for model in AVAILABLE_MODELS:
                        try:
                            resp = client.models.generate_content(model=model, contents=prompt)
                            st.markdown(resp.text)
                            st.session_state.chat_messages.append({"role": "assistant", "content": resp.text})
                            answered = True
                            break
                        except Exception:
                            continue
                    if not answered:
                        st.error("답변 생성에 실패했습니다.")

# ----------------- TAB 3: Cross-Synthesis -----------------
with tab3:
    st.header("지식 간 상호작용 메타 융합 (Cross-Report Synthesis)")
    st.caption("독립된 2개 이상의 리포트를 결합하여 숨겨진 상호 인과관계와 2차 파급효과를 도출합니다.")
    
    reports = load_all_reports()
    if len(reports) < 2:
        st.info("교차 융합을 위해 최소 2개 이상의 리포트가 필요합니다.")
    else:
        report_options = {os.path.basename(f): f for f in reports}
        selected_for_fusion = st.multiselect(
            "융합할 리포트를 2개 이상 선택하세요",
            list(report_options.keys()),
            max_selections=4
        )
        
        if st.button("🧬 선택 문서 메타 융합 시작") and len(selected_for_fusion) >= 2:
            combined_docs = ""
            titles = []
            for name in selected_for_fusion:
                path = report_options[name]
                titles.append(name.split("_")[1] if "_" in name else name)
                with open(path, "r", encoding="utf-8") as f:
                    combined_docs += f"\n\n==================== [문서: {name}] ====================\n{f.read()}"
                    
            meta_topic = " & ".join(titles[:3])
            current_year = datetime.now().year
            fusion_prompt = f"""
당신은 거시 지식 합성(Meta-Synthesis) 수석 아키텍트입니다. 현재는 {current_year}년입니다.
아래 독립된 지식 리포트들을 결합하여 두 시스템이 만났을 때 드러나는 구조적 상호작용과 메타 리포트를 작성하세요.

# [{meta_topic}] 지식 융합 & 상호작용 메타 리포트
## 0. Executive Core Insight (융합 핵심 통찰)
## 1. Interconnected Mechanics (상호 인과 메커니즘 및 피드백 루프)
## 2. Clash of Constraints: Real vs Fake (제약의 충돌과 상충관계)
## 3. Second-Order & Third-Order Systemic Effects (2차·3차 거시 파급 효과)
## 4. Unified 10x Strategic Playbook (통합 10배 실행 레버리지)
## 5. Visual Mindmap & Structural Hierarchy (통합 마인드맵: 순수 탭 들여쓰기 트리 + mermaid mindmap 코드)

[원천 지식 문서]:
{combined_docs}
"""
            with st.spinner("메타 융합 리포트 생성 중..."):
                client = genai.Client(api_key=GEMINI_API_KEY)
                for model in AVAILABLE_MODELS:
                    try:
                        res = client.models.generate_content(model=model, contents=fusion_prompt)
                        saved = save_report_to_file(f"융합_{meta_topic}", "META_SYNTHESIS", res.text)
                        st.success(f"메타 리포트 저장 완료: {saved}")
                        
                        mermaid_blocks = re.findall(r'```mermaid([\s\S]*?)```', res.text)
                        if mermaid_blocks:
                            st.subheader("🗺️ 융합 지식 구조 마인드맵")
                            for mb in mermaid_blocks:
                                render_mermaid(mb)
                        st.markdown(res.text)
                        break
                    except Exception:
                        continue

# ----------------- TAB 4: Knowledge Audit -----------------
with tab4:
    st.header("지식 베이스 스트레스 테스트 & 공백 감사 (Audit)")
    st.caption("보관된 전체 문서를 비판적으로 스캔하여 논리적 모순과 취약한 가정, 누락된 사각지대를 찾아냅니다.")
    
    if st.button("🛡️ 전수 지식 감사 실행"):
        reports = load_all_reports()
        if not reports:
            st.warning("감사할 리포트가 없습니다.")
        else:
            all_summary = ""
            for idx, fpath in enumerate(reports, 1):
                fname = os.path.basename(fpath)
                with open(fpath, "r", encoding="utf-8") as f:
                    all_summary += f"\n\n--- [문서 {idx}: {fname}] ---\n{f.read()[:2500]}"
            
            audit_prompt = f"""
당신은 제1원리 기반의 냉혹한 수석 지식 감사관입니다.
보관된 지식 리포트들을 전수 분석하여 신뢰성을 극대화하기 위한 감사 보고서를 작성하세요.

# 🛡️ Second Brain 지식 스트레스 테스트 & 공백 감사 보고서
## 1. Contradictions & Temporal Conflicts (모순 및 시계열 충돌 감지)
## 2. Fragile Assumptions & Unproven Beliefs (취약한 가정과 가짜 제약 감사)
## 3. Critical Knowledge Gaps (치명적 지식 공백 및 사각지대)
## 4. Next Research Quests (다음 채굴 우선순위 키워드 추천 3가지)

[지식 베이스 요약]:
{all_summary}
"""
            with st.spinner("지식 정합성 스트레스 테스트 중..."):
                client = genai.Client(api_key=GEMINI_API_KEY)
                for model in AVAILABLE_MODELS:
                    try:
                        res = client.models.generate_content(model=model, contents=audit_prompt)
                        saved = save_report_to_file("지식_감사_스트레스테스트", "AUDIT_REPORT", res.text)
                        st.success(f"감사 완료! 보고서 보관: {saved}")
                        st.markdown(res.text)
                        break
                    except Exception:
                        continue

# ----------------- TAB 5: Reader & Mindmap -----------------
with tab5:
    st.header("📖 리포트 열람실 & 마인드맵 시각화")
    
    if os.path.exists("reports/README.md"):
        with st.expander("📊 마스터 지식 자산 카탈로그 전체 보기", expanded=False):
            with open("reports/README.md", "r", encoding="utf-8") as f:
                readme_text = f.read()
            st.markdown(readme_text)
            
    st.markdown("---")
    
    if selected_report_file and os.path.exists(selected_report_file):
        with open(selected_report_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        st.subheader(f"📄 {os.path.basename(selected_report_file)}")
        
        mermaid_matches = re.findall(r'```mermaid([\s\S]*?)```', content)
        if mermaid_matches:
            st.info("💡 본 리포트의 Mermaid 구조도를 그래픽 마인드맵 차트로 시각화했습니다:")
            for mm_code in mermaid_matches:
                render_mermaid(mm_code)
                
        st.markdown(content)
    else:
        st.info("사이드바에서 열람할 리포트를 선택해 주세요.")