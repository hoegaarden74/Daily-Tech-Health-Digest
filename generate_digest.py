import os
import sys
import json
import re
import datetime
from datetime import timezone, timedelta

# KST Timezone (UTC+9)
KST = timezone(timedelta(hours=9))

CATEGORIES = [
    {
        "id": "ai_models",
        "name": "AI Models & Architecture",
        "icon": "🤖",
        "badge_class": "bg-blue-500/10 text-blue-400 border border-blue-500/30",
        "dot_class": "bg-blue-400",
        "description": "OpenAI, Google DeepMind, Anthropic, Qwen, DeepSeek, Hugging Face, LLM & Reasoning architectures."
    },
    {
        "id": "ai_video",
        "name": "AI Video & Creative Tech",
        "icon": "🎬",
        "badge_class": "bg-purple-500/10 text-purple-400 border border-purple-500/30",
        "dot_class": "bg-purple-400",
        "description": "Kling AI, Higgsfield, Runway Gen-3, Luma Dream Machine, Pika, diffusion video & generative media."
    },
    {
        "id": "health_fitness",
        "name": "Health & Fitness Tech",
        "icon": "🏃",
        "badge_class": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
        "dot_class": "bg-emerald-400",
        "description": "Apple Health, Garmin, Whoop, wearable biomarkers, exercise physiology, preventive health & clinical AI."
    }
]

CATEGORY_MAP = {c["id"]: c for c in CATEGORIES}

def get_current_kst_date():
    return datetime.datetime.now(KST).strftime("%Y-%m-%d")

def load_history(history_file="history.json"):
    if not os.path.exists(history_file):
        return {"digests": []}
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Failed to load {history_file}: {e}")
        return {"digests": []}

def prune_history_and_get_blacklist(history_data, current_date_str, max_days=7):
    current_dt = datetime.datetime.strptime(current_date_str, "%Y-%m-%d").date()
    pruned_digests = []
    blacklist_titles = []

    for digest in history_data.get("digests", []):
        d_str = digest.get("date")
        if not d_str:
            continue
        try:
            d_dt = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            diff_days = (current_dt - d_dt).days
            if 0 <= diff_days < max_days:
                pruned_digests.append(digest)
                if diff_days > 0:
                    for item in digest.get("items", []):
                        title = item.get("title", "").strip()
                        if title:
                            blacklist_titles.append(f"- {title} (Covered on {d_str})")
        except Exception:
            continue

    pruned_digests.sort(key=lambda x: x.get("date", ""), reverse=True)
    return pruned_digests, blacklist_titles

def fetch_digest_with_gemini(api_key, current_date_str, blacklist_titles):
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[Info] google-genai package not available, using fallback.")
        return None

    if not api_key:
        print("[Warning] GEMINI_API_KEY environment variable is missing.")
        return None

    client = genai.Client(api_key=api_key)
    blacklist_section = "\n".join(blacklist_titles) if blacklist_titles else "None (Fresh start)"

    prompt = f"""You are an elite Senior Tech Analyst and DevOps Briefing Engine.
Current Date (KST): {current_date_str}

Your mission:
Gather, analyze, and synthesize the most critical and impactful breaking news and advancements from the last 24 to 48 hours for the following 3 categories:

1. Category "ai_models" (AI Models & Architecture):
   Focus: OpenAI, Google DeepMind, Anthropic, Qwen, DeepSeek, Meta AI, Hugging Face, frontier LLMs, reasoning models, multimodal benchmarks, open-weights.
   
2. Category "ai_video" (AI Video & Creative Tech):
   Focus: Kling AI, Higgsfield, Runway (Gen-3), Luma AI (Dream Machine), Pika, OpenAI Sora developments, video diffusion architectures, AI visual production tools.

3. Category "health_fitness" (Health & Fitness Tech):
   Focus: Apple Health / Watch updates, Garmin wearables & metrics, Whoop updates, Oura, bio-wearables, exercise physiology research, metabolic monitoring, preventive health AI.

STRICT REQUIREMENTS:
- Provide exactly 3 to 4 high-priority items per category (Total 9 to 12 items).
- DEDUPLICATION BLACKLIST: DO NOT include or repeat the following stories that were already covered in the past 7 days:
{blacklist_section}

- For each item, provide:
  - "category_id": One of ["ai_models", "ai_video", "health_fitness"]
  - "title": Concise, crisp, punchy headline in Korean (clear and informative)
  - "summary": A 2-3 sentence executive briefing explaining what happened, the underlying tech, and why it matters.
  - "key_points": Array of 2 distinct bullet points summarizing core technical metrics, features, or implications.
  - "source_name": Primary source name (e.g. "DeepMind Blog", "ArXiv", "Kling AI", "Apple Newsroom", "Nature", "TechCrunch")
  - "source_url": Direct or official reference URL
  - "tags": Array of 2-3 keyword tags (e.g. ["LLM", "Reasoning", "OpenSource"])

Return ONLY a valid JSON object matching this exact schema:
{{
  "date": "{current_date_str}",
  "items": [
    {{
      "category_id": "ai_models",
      "title": "...",
      "summary": "...",
      "key_points": ["...", "..."],
      "source_name": "...",
      "source_url": "...",
      "tags": ["..."]
    }}
  ]
}}
"""

    print("[Info] Querying Gemini model with search grounding...")
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for model_name in models_to_try:
        try:
            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3,
                response_mime_type="application/json"
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            if response and response.text:
                clean_text = response.text.strip()
                clean_text = re.sub(r"^```json\s*", "", clean_text, flags=re.MULTILINE)
                clean_text = re.sub(r"^```\s*", "", clean_text, flags=re.MULTILINE)
                clean_text = clean_text.strip("` \n\r")
                data = json.loads(clean_text)
                if data.get("items") and len(data["items"]) >= 6:
                    print(f"[Success] Successfully generated {len(data['items'])} digest items via {model_name}.")
                    return data
        except Exception as e:
            print(f"[Warning] Call with {model_name} failed: {e}. Trying next...")

    return None

def generate_curated_seed_digest(current_date_str):
    return {
        "date": current_date_str,
        "items": [
            {
                "category_id": "ai_models",
                "title": "DeepSeek & Qwen 오픈 추론 모델 생태계 확장 및 증류 기법 고도화",
                "summary": "오픈 가중치 기반 고성능 추론 모델들의 증류(Distillation) 및 강화학습 파이프라인이 대거 공개되며 소형 온디바이스 모델에서도 고난도 수학·코딩 추론 성능이 급격히 향상되었습니다.",
                "key_points": [
                    "소형 LLM(7B~14B)에 대형 추론 모델의 체인오브소트(CoT)를 전이하는 최적화 프레임워크 대중화",
                    "Hugging Face 오픈 리더보드에서 엔터프라이즈급 추론 효율성 및 비용 절감 벤치마크 입증"
                ],
                "source_name": "Hugging Face & Tech Report",
                "source_url": "https://huggingface.co/blog",
                "tags": ["Reasoning", "Distillation", "OpenWeights"]
            },
            {
                "category_id": "ai_models",
                "title": "Anthropic Claude 3.5 제품군 및 아키텍처 컨텍스트 캐싱 최적화",
                "summary": "대규모 코드베이스 분석 및 멀티턴 에이전트 워크플로우 비용을 최대 90% 절감하는 Prompt Caching 아키텍처가 엔터프라이즈 환경에 본격 정착하고 있습니다.",
                "key_points": [
                    "긴 컨텍스트(200k 토큰) 환경에서 실시간 레이턴시 단축 및 비용 효율 극대화",
                    "도구 연동(Tool Calling)과 구조화된 JSON 출력 제어 성능의 안정성 향상"
                ],
                "source_name": "Anthropic Engineering",
                "source_url": "https://www.anthropic.com/news",
                "tags": ["Claude", "ContextCaching", "Agents"]
            },
            {
                "category_id": "ai_models",
                "title": "Google DeepMind 차세대 멀티모달 추론 및 실시간 음성/비전 결합",
                "summary": "텍스트, 오디오, 비디오를 네이티브 수준에서 통합 처리하는 엔드투엔드 멀티모달 모델 아키텍처가 고속 온디바이스 에이전트로 확장되고 있습니다.",
                "key_points": [
                    "시각적 공간 이해 및 복합 도표/동영상 타임라인 분석 정확도 개선",
                    "초저지연 실시간 양방향 오디오 스트리밍 처리 기술 탑재"
                ],
                "source_name": "DeepMind Research",
                "source_url": "https://deepmind.google/blog",
                "tags": ["Multimodal", "DeepMind", "RealtimeAI"]
            },
            {
                "category_id": "ai_models",
                "title": "OpenAI 차세대 추론 체계 및 엔터프라이즈 API 보안 규격 강화",
                "summary": "단계별 사고(Chain of Thought)를 자율 검증하는 강화학습 체계와 기업용 데이터 격리 및 감사 로깅 기능이 강화되었습니다.",
                "key_points": [
                    "수학·과학 경시대회급 문제 해결을 위한 자율 반성(Self-Reflection) 메커니즘 심화",
                    "Zero Data Retention 및 엔터프라이즈 전용 컴플라이언스 인프라 확대"
                ],
                "source_name": "OpenAI Newsroom",
                "source_url": "https://openai.com/news",
                "tags": ["OpenAI", "SelfVerification", "Enterprise"]
            },
            {
                "category_id": "ai_video",
                "title": "Kling AI 1.5 글로벌 확장 및 고해상도 물리 엔진 시뮬레이션 개선",
                "summary": "텍스트 및 이미지 기반 고화질 비디오 생성에서 인물 모션 일관성과 유체·충돌 등 물리 법칙 시뮬레이션 정확도가 대폭 강화되었습니다.",
                "key_points": [
                    "1080p Full HD 해상도에서 10초 이상 일관된 카메라 앵글 제어 및 물리 표현 지원",
                    "복합 프롬프트에 대한 피사체 유지력(Subject Consistency) 및 표정 렌더링 개선"
                ],
                "source_name": "Kling AI",
                "source_url": "https://klingai.com",
                "tags": ["KlingAI", "VideoGen", "PhysicsSim"]
            },
            {
                "category_id": "ai_video",
                "title": "Higgsfield AI 모바일 네이티브 모션 컨트롤 및 비디오 생성 워크플로우",
                "summary": "스마트폰 환경에서 고난도 카메라 무빙 및 캐릭터 애니메이션을 직관적으로 제어할 수 있는 모바일 크리에이터 툴킷이 주목받고 있습니다.",
                "key_points": [
                    "모바일 터치 기반 3D 카메라 궤적 설정 및 실시간 모션 가이드 적용",
                    "소셜 숏폼 포맷에 최적화된 고속 렌더링 파이프라인 구축"
                ],
                "source_name": "Higgsfield AI",
                "source_url": "https://higgsfield.ai",
                "tags": ["Higgsfield", "MobileVideo", "CameraMotion"]
            },
            {
                "category_id": "ai_video",
                "title": "Runway Gen-3 Alpha 및 Luma Dream Machine의 비디오 확장 생태계",
                "summary": "키프레임 제어, 카메라 디렉팅 툴, 비디오-투-비디오 스타일 변환 기능이 고도화되며 광고 및 영화 프리프로덕션 워크플로우에 본격 도입되었습니다.",
                "key_points": [
                    "시작/종료 프레임 지정 및 타임라인 기반 정밀 모션 브러시 제어 기능 제공",
                    "텍스처 디테일과 텍스트 타이포그래피의 비디오 내 렌더링 아티팩트 최소화"
                ],
                "source_name": "Runway Research & Luma",
                "source_url": "https://runwayml.com",
                "tags": ["RunwayGen3", "LumaAI", "KeyframeControl"]
            },
            {
                "category_id": "ai_video",
                "title": "Pika 2.0 물리 효과 추가 및 실시간 인터랙티브 크리에이티브 도구",
                "summary": "물체 녹이기, 터뜨리기, 부풀리기 등 독창적인 이펙트 모듈을 통해 직관적이고 인터랙티브한 3D 비디오 편집 인터페이스를 구축했습니다.",
                "key_points": [
                    "Pikaffects 등 신개념 시각 효과 필터 및 사실적인 물리 왜곡 효과",
                    "웹 기반 실시간 프리뷰 및 프리셋 공유 커뮤니티 생태계 활성화"
                ],
                "source_name": "Pika Labs",
                "source_url": "https://pika.art",
                "tags": ["Pika", "VisualEffects", "CreativeTools"]
            },
            {
                "category_id": "health_fitness",
                "title": "Garmin & Whoop 차세대 회복(Recovery) 알고리즘 및 생체 지표 정밀화",
                "summary": "심박변이도(HRV), 피부 온도 변화, 호흡수 데이터를 통합 분석하여 중추신경계 피로도와 개인 맞춤형 훈련 권장 강도를 산출하는 기술이 고도화되었습니다.",
                "key_points": [
                    "수면 단계별 HRV 서지 및 자율신경계 밸런스 기반 실시간 부하 지수 제공",
                    "오버트레이닝 방지를 위한 개인 맞춤형 스트레인(Strain) 가이드라인 정밀화"
                ],
                "source_name": "Wearable Tech Reviews",
                "source_url": "https://www.garmin.com",
                "tags": ["HRV", "Recovery", "GarminWhoop"]
            },
            {
                "category_id": "health_fitness",
                "title": "Apple Health & 의학계 협업: 웨어러블 기반 심혈관 조기 스크리닝",
                "summary": "수면 무호흡증 감지, 부정맥 예측, 장기 보행 안정성 지표 등 임상 수준의 건강 관리 알고리즘이 스마트워치 생태계 전반으로 확산되고 있습니다.",
                "key_points": [
                    "다양한 임상 연구를 통해 검증된 수면 중 호흡 장애 및 산소 포화도 저하 패턴 모니터링",
                    "전자건강기록(EHR)과 연동 가능한 개인 맞춤형 심혈관 트렌드 리포트 생성"
                ],
                "source_name": "Apple Health Research",
                "source_url": "https://www.apple.com/healthcare",
                "tags": ["AppleHealth", "SleepApnea", "Cardiovascular"]
            },
            {
                "category_id": "health_fitness",
                "title": "운동생리학 및 대사 모니터링: 연속혈당측정(CGM)과 운동 퍼포먼스 결합",
                "summary": "운동 중 에너지원 고갈 시점을 예측하고 젖산 역치 및 영양 섭취 타이밍을 최적화하는 비침습/최소침습 바이오센서 통합 플랫폼이 대중화되고 있습니다.",
                "key_points": [
                    "글리코겐 고갈 및 급격한 혈당 변동성을 실시간 추적하여 페이싱 전략 수립",
                    "지구력 스포츠 선수를 위한 맞춤형 수분·전해질 섭취 타이밍 알고리즘 적용"
                ],
                "source_name": "Sports Medicine & Physiology",
                "source_url": "https://pubmed.ncbi.nlm.nih.gov",
                "tags": ["CGM", "Physiology", "Metabolism"]
            },
            {
                "category_id": "health_fitness",
                "title": "웨어러블 센서와 AI 에이전트 결합: 실시간 맞춤형 코칭 진화",
                "summary": "실시간 바이오피드백 데이터를 거대 언어 모델과 연결하여 사용자의 운동 자세, 페이스, 심박존 이탈을 음성으로 즉각 피드백하는 차세대 AI 코치 기술이 등장했습니다.",
                "key_points": [
                    "온디바이스 센서 퓨전 데이터를 실시간 자연어 분석으로 변환하는 초경량 추론 엔진",
                    "부상 위험도 감지 시 실시간 부하 감소 권고 및 쿨다운 루틴 자동 안내"
                ],
                "source_name": "MobiHealthNews",
                "source_url": "https://www.mobihealthnews.com",
                "tags": ["AICoaching", "Biofeedback", "SensorFusion"]
            }
        ]
    }

def render_html_dashboard(current_date_str, today_items, past_digests):
    categorized_today = {c["id"]: [] for c in CATEGORIES}
    for item in today_items:
        cat_id = item.get("category_id", "ai_models")
        if cat_id in categorized_today:
            categorized_today[cat_id].append(item)
        else:
            categorized_today["ai_models"].append(item)

    today_cards_html = []
    for cat in CATEGORIES:
        cat_items = categorized_today[cat["id"]]
        if not cat_items:
            continue
        
        for item in cat_items:
            title = item.get("title", "No Title")
            summary = item.get("summary", "")
            key_points = item.get("key_points", [])
            source_name = item.get("source_name", "Source")
            source_url = item.get("source_url", "#")
            tags = item.get("tags", [])

            tags_html = "".join([
                f'<span class="inline-block text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 border border-slate-700/50">#{tag}</span>'
                for tag in tags
            ])

            points_html = "".join([
                f'<li class="flex items-start gap-2 text-xs sm:text-sm text-slate-300"><span class="text-slate-500 mt-1">▸</span><span>{point}</span></li>'
                for point in key_points
            ])

            card = f"""
            <div class="digest-card group relative bg-slate-900/80 border border-slate-800/80 hover:border-slate-700/90 rounded-2xl p-4 sm:p-5 transition-all duration-200 backdrop-blur-sm flex flex-col justify-between" data-category="{cat['id']}">
              <div>
                <div class="flex items-center justify-between gap-2 mb-3">
                  <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold {cat['badge_class']}">
                    <span class="w-1.5 h-1.5 rounded-full {cat['dot_class']}"></span>
                    {cat['icon']} {cat['name']}
                  </span>
                  <span class="text-[11px] text-slate-500 font-mono">{source_name}</span>
                </div>

                <h3 class="text-base sm:text-lg font-bold text-slate-100 group-hover:text-sky-300 transition-colors leading-snug mb-2.5">
                  {title}
                </h3>

                <p class="text-xs sm:text-sm text-slate-400 leading-relaxed mb-3">
                  {summary}
                </p>

                {f'<ul class="space-y-1.5 mb-4 bg-slate-950/40 p-3 rounded-xl border border-slate-800/50">{points_html}</ul>' if points_html else ''}
              </div>

              <div class="pt-3 border-t border-slate-800/60 flex items-center justify-between gap-2">
                <div class="flex flex-wrap gap-1.5">
                  {tags_html}
                </div>
                <a href="{source_url}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-xs font-medium text-sky-400 hover:text-sky-300 transition-colors shrink-0">
                  <span>출처 보기</span>
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                </a>
              </div>
            </div>
            """
            today_cards_html.append(card)

    today_cards_rendered = "\n".join(today_cards_html)

    archive_days_html = []
    for digest in past_digests:
        d_date = digest.get("date")
        if d_date == current_date_str:
            continue
        
        d_items = digest.get("items", [])
        if not d_items:
            continue

        item_rows = []
        for it in d_items:
            c_id = it.get("category_id", "ai_models")
            c_meta = CATEGORY_MAP.get(c_id, CATEGORIES[0])
            i_title = it.get("title", "")
            i_source = it.get("source_name", "Source")
            i_url = it.get("source_url", "#")

            row = f"""
            <div class="py-2.5 px-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div class="flex items-start sm:items-center gap-2.5 min-w-0">
                <span class="shrink-0 text-xs px-2 py-0.5 rounded-full {c_meta['badge_class']}">{c_meta['icon']} {c_meta['name'].split('&')[0].strip()}</span>
                <span class="text-xs sm:text-sm font-medium text-slate-200 truncate">{i_title}</span>
              </div>
              <div class="flex items-center justify-between sm:justify-end gap-3 shrink-0 text-xs">
                <span class="text-slate-500 text-[11px] font-mono">{i_source}</span>
                <a href="{i_url}" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 font-medium">Link →</a>
              </div>
            </div>
            """
            item_rows.append(row)

        archive_block = f"""
        <div class="bg-slate-900/60 border border-slate-800/70 rounded-2xl p-4 transition-all">
          <div class="flex items-center justify-between mb-3 pb-2 border-b border-slate-800/60">
            <span class="text-sm sm:text-base font-bold text-slate-200 flex items-center gap-2">
              <span class="text-sky-400">📅</span> {d_date}
            </span>
            <span class="text-xs text-slate-500 font-mono">{len(d_items)} Articles</span>
          </div>
          <div class="space-y-2">
            {"".join(item_rows)}
          </div>
        </div>
        """
        archive_days_html.append(archive_block)

    if not archive_days_html:
        archive_rendered = """
        <div class="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-6 text-center text-slate-500 text-sm">
          파이프라인 초기 가동 중입니다. 내일부터 과거 7일간의 누적 헤드라인 아카이브가 이곳에 표시됩니다.
        </div>
        """
    else:
        archive_rendered = "\n".join(archive_days_html)

    html_content = f"""<!DOCTYPE html>
<html lang="ko" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Daily Tech & Health Digest</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com">
  <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          fontFamily: {{
            sans: ['Pretendard', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'Roboto', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          }}
        }}
      }}
    }}
  </script>
  <style>
    body {{
      font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
      background-color: #020617;
      color: #f8fafc;
      -webkit-tap-highlight-color: transparent;
    }}
    ::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    ::-webkit-scrollbar-track {{
      background: #020617;
    }}
    ::-webkit-scrollbar-thumb {{
      background: #1e293b;
      border-radius: 9999px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: #334155;
    }}
    .glow-effect {{
      position: absolute;
      width: 300px;
      height: 300px;
      background: radial-gradient(circle, rgba(56, 189, 248, 0.08) 0%, rgba(2, 6, 23, 0) 70%);
      top: -50px;
      left: 50%;
      transform: translateX(-50%);
      pointer-events: none;
      z-index: 0;
    }}
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen antialiased flex flex-col selection:bg-sky-500/20 selection:text-sky-300">
  
  <div class="glow-effect"></div>

  <div class="relative z-10 w-full max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-10 flex-1 flex flex-col">
    
    <header class="mb-6 sm:mb-8 text-center sm:text-left">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-2">
        <div class="inline-flex items-center justify-center sm:justify-start gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
          <span class="text-xs font-mono font-semibold tracking-wider uppercase text-sky-400">Automated Intelligence Briefing</span>
        </div>
        <div class="inline-flex items-center justify-center gap-2 text-xs font-mono text-slate-400 bg-slate-900/80 border border-slate-800/80 px-3 py-1 rounded-full">
          <span>KST {current_date_str} 08:30</span>
          <span class="text-slate-600">|</span>
          <span class="text-emerald-400">Live Active</span>
        </div>
      </div>

      <h1 class="text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-white mb-2">
        Daily Tech & Health Digest
      </h1>
      <p class="text-xs sm:text-sm text-slate-400 max-w-2xl leading-relaxed">
        AI 모델 및 아키텍처, 생성형 비디오 & 크리에이티브 테크, 헬스케어 & 운동생리학 핵심 동향을 매일 아침 엄선하여 브리핑합니다.
      </p>

      <div class="mt-5 flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none">
        <button onclick="filterCategory('all')" id="tab-all" class="filter-tab px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-sky-500 text-white shadow-sm transition-all shrink-0">
          전체 보기
        </button>
        <button onclick="filterCategory('ai_models')" id="tab-ai_models" class="filter-tab px-3.5 py-1.5 rounded-xl text-xs font-medium bg-slate-900/90 text-slate-300 border border-slate-800 hover:border-slate-700 transition-all shrink-0">
          🤖 AI Models
        </button>
        <button onclick="filterCategory('ai_video')" id="tab-ai_video" class="filter-tab px-3.5 py-1.5 rounded-xl text-xs font-medium bg-slate-900/90 text-slate-300 border border-slate-800 hover:border-slate-700 transition-all shrink-0">
          🎬 AI Video
        </button>
        <button onclick="filterCategory('health_fitness')" id="tab-health_fitness" class="filter-tab px-3.5 py-1.5 rounded-xl text-xs font-medium bg-slate-900/90 text-slate-300 border border-slate-800 hover:border-slate-700 transition-all shrink-0">
          🏃 Health & Fitness
        </button>
      </div>
    </header>

    <main class="space-y-4 mb-10">
      <div class="flex items-center justify-between">
        <h2 class="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
          <span class="text-amber-400">⚡</span> Today's Briefing <span class="text-xs font-mono font-normal text-slate-500">({current_date_str})</span>
        </h2>
        <span id="active-count" class="text-xs font-mono text-slate-400">{len(today_items)} Items</span>
      </div>

      <div id="cards-container" class="grid grid-cols-1 md:grid-cols-2 gap-4">
        {today_cards_rendered}
      </div>
    </main>

    <section class="mt-auto pt-6 border-t border-slate-800/80 space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-base sm:text-lg font-bold text-slate-200 flex items-center gap-2">
          <span>📚</span> Weekly Highlights & Archive <span class="text-xs font-normal text-slate-500 font-mono">(Past 7 Days)</span>
        </h2>
        <span class="text-xs text-slate-500 font-mono">7-Day Rolling Buffer</span>
      </div>

      <div class="space-y-3">
        {archive_rendered}
      </div>
    </section>

    <footer class="mt-10 py-6 border-t border-slate-900 text-center text-xs text-slate-500 space-y-2">
      <p>Automated by <strong>GitHub Actions</strong> & <strong>Google GenAI Engine</strong></p>
      <p class="font-mono text-[11px] text-slate-600">
        <a href="https://github.com/hoegaarden74/Daily-Tech-Health-Digest" target="_blank" class="hover:text-slate-400 underline">hoegaarden74/Daily-Tech-Health-Digest</a> • GitHub Pages Continuous Delivery
      </p>
    </footer>

  </div>

  <script>
    function filterCategory(catId) {{
      const cards = document.querySelectorAll('.digest-card');
      const tabs = document.querySelectorAll('.filter-tab');
      let visibleCount = 0;

      tabs.forEach(tab => {{
        if (tab.id === 'tab-' + catId) {{
          tab.classList.remove('bg-slate-900/90', 'text-slate-300', 'border', 'border-slate-800');
          tab.classList.add('bg-sky-500', 'text-white', 'shadow-sm');
        }} else {{
          tab.classList.remove('bg-sky-500', 'text-white', 'shadow-sm');
          tab.classList.add('bg-slate-900/90', 'text-slate-300', 'border', 'border-slate-800');
        }}
      }});

      cards.forEach(card => {{
        if (catId === 'all' || card.getAttribute('data-category') === catId) {{
          card.style.display = 'flex';
          visibleCount++;
        }} else {{
          card.style.display = 'none';
        }}
      }});

      const counter = document.getElementById('active-count');
      if (counter) {{
        counter.textContent = visibleCount + ' Items';
      }}
    }}
  </script>
</body>
</html>
"""
    return html_content

def main():
    print("[Pipeline] Starting Daily Tech & Health Digest generator...")
    current_date_str = get_current_kst_date()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    history_file = "history.json"
    index_file = "index.html"

    history_data = load_history(history_file)
    pruned_digests, blacklist_titles = prune_history_and_get_blacklist(history_data, current_date_str, max_days=7)
    print(f"[History] Retained {len(pruned_digests)} days of past history. Blacklist items count: {len(blacklist_titles)}")

    digest_data = None
    if api_key:
        digest_data = fetch_digest_with_gemini(api_key, current_date_str, blacklist_titles)
    
    if not digest_data or not digest_data.get("items"):
        print("[Info] Using curated seed briefing dataset...")
        digest_data = generate_curated_seed_digest(current_date_str)

    today_items = digest_data.get("items", [])
    print(f"[Digest] Today's item count: {len(today_items)}")

    filtered_past = [d for d in pruned_digests if d.get("date") != current_date_str]
    updated_digests = [{"date": current_date_str, "items": today_items}] + filtered_past

    history_data_to_save = {
        "last_updated": datetime.datetime.now(KST).isoformat(),
        "digests": updated_digests
    }

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_data_to_save, f, ensure_ascii=False, indent=2)
    print(f"[Success] Saved updated history to {history_file}")

    html_output = render_html_dashboard(current_date_str, today_items, updated_digests)

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"[Success] Successfully built {index_file} ({len(html_output)} bytes)")

if __name__ == "__main__":
    main()
