import os
import sys
import json
import re
import datetime
from datetime import timezone, timedelta
import urllib.request
import xml.etree.ElementTree as ET

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
    blacklist_set = set()

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
                            blacklist_titles.append(f"- [{d_str}] {title}")
                            blacklist_set.add(title.lower())
        except Exception as e:
            continue

    pruned_digests.sort(key=lambda x: x.get("date", ""), reverse=True)
    return pruned_digests, blacklist_titles, blacklist_set

def extract_json_from_text(text):
    if not text:
        return None
    code_block = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.IGNORECASE)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except Exception:
            pass

    brace_match = re.search(r'(\{[\s\S]*\})', text)
    if brace_match:
        try:
            return json.loads(brace_match.group(1).strip())
        except Exception:
            pass

    try:
        return json.loads(text.strip())
    except Exception:
        return None

def fetch_digest_with_gemini(api_key, current_date_str, blacklist_titles):
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    if not api_key:
        return None

    client = genai.Client(api_key=api_key)
    blacklist_section = "\n".join(blacklist_titles) if blacklist_titles else "None (Fresh start)"

    prompt = f"""You are an elite Senior Tech Analyst and Real-time Briefing Engine.
Current Date (KST): {current_date_str}

YOUR OBJECTIVE:
Find, synthesize, and report the most critical, fresh, and impactful breaking news and technical advancements that occurred in the LAST 24 TO 48 HOURS for each of the following 3 categories:

1. Category "ai_models" (AI Models & Architecture):
   Focus: New model releases, weights, research papers, architectures, benchmarks from OpenAI, DeepMind, Anthropic, Qwen, DeepSeek, Mistral, Meta AI, Hugging Face, ArXiv.

2. Category "ai_video" (AI Video & Creative Tech):
   Focus: New updates, generative video models, motion tools, releases from Kling AI, Higgsfield, Runway, Luma AI, Pika, OpenAI Sora, visual diffusion techniques.

3. Category "health_fitness" (Health & Fitness Tech):
   Focus: Apple Health / Watch updates, Garmin, Whoop, Oura, bio-wearables, exercise physiology findings, metabolic sensors, clinical health AI.

🚨 CRITICAL DEDUPLICATION RULE (ABSOLUTELY NO REPEATS):
The following stories have ALREADY been covered and archived in the past 7 days.
YOU MUST NOT repeat or rephrase any of these stories:
{blacklist_section}

You MUST find COMPLETELY NEW and DIFFERENT events, research papers, model releases, or industry announcements from today or the past 24-48 hours.

OUTPUT SPECIFICATIONS:
- Exactly 3 to 4 items per category (Total 9 to 12 items).
- Each item MUST contain:
  * "category_id": One of ["ai_models", "ai_video", "health_fitness"]
  * "title": Clear, professional, informative headline in Korean.
  * "summary": 2-3 sentences executive summary explaining what happened, the underlying tech/mechanism, and why it matters.
  * "key_points": Array of 2 distinct bullet points highlighting technical details or key metrics.
  * "source_name": Credible source name (e.g., "DeepMind Blog", "ArXiv", "Hugging Face", "Apple Newsroom", "Nature Medicine", "TechCrunch")
  * "source_url": Direct link to the source or article.
  * "tags": Array of 2-3 keyword tags (e.g., ["LLM", "Reasoning", "OpenWeights"])

Format your response strictly as a JSON object matching this schema:
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

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for model_name in models_to_try:
        try:
            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            if response and response.text:
                parsed_json = extract_json_from_text(response.text)
                if parsed_json and parsed_json.get("items") and len(parsed_json["items"]) >= 6:
                    return parsed_json
        except Exception as e:
            print(f"[Warning] Model {model_name} with search tool failed: {e}")

        try:
            config = types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json"
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            if response and response.text:
                parsed_json = extract_json_from_text(response.text)
                if parsed_json and parsed_json.get("items") and len(parsed_json["items"]) >= 6:
                    return parsed_json
        except Exception as e:
            print(f"[Warning] Direct JSON call with {model_name} failed: {e}")

    return None

def is_duplicate_item(item_title, blacklist_set):
    clean_title = item_title.strip().lower()
    if clean_title in blacklist_set:
        return True
    
    item_tokens = set(re.findall(r'[a-zA-Z0-9가-힣]{2,}', clean_title))
    if not item_tokens:
        return False
        
    for blacklisted in blacklist_set:
        b_tokens = set(re.findall(r'[a-zA-Z0-9가-힣]{2,}', blacklisted))
        if not b_tokens:
            continue
        overlap = len(item_tokens.intersection(b_tokens))
        ratio = overlap / max(len(item_tokens), len(b_tokens))
        if ratio > 0.7:
            return True
    return False

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
          과거 7일간의 누적 헤드라인 아카이브가 이곳에 순차적으로 보관됩니다.
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
    pruned_digests, blacklist_titles, blacklist_set = prune_history_and_get_blacklist(history_data, current_date_str, max_days=7)
    print(f"[History] Retained {len(pruned_digests)} days. Blacklisted stories: {len(blacklist_titles)}")

    digest_data = None
    if api_key:
        digest_data = fetch_digest_with_gemini(api_key, current_date_str, blacklist_titles)
    else:
        print("[Warning] No GEMINI_API_KEY provided in environment.")

    today_items = []
    if digest_data and digest_data.get("items"):
        raw_items = digest_data["items"]
        for it in raw_items:
            t = it.get("title", "")
            if not is_duplicate_item(t, blacklist_set):
                today_items.append(it)
            else:
                print(f"[Dedup] Filtered out duplicate story from previous days: {t}")

    if not today_items:
        if digest_data and digest_data.get("items"):
            today_items = digest_data["items"]
        else:
            print("[Info] Gemini call returned empty. Using fallback generation...")
            today_items = [
                {
                    "category_id": "ai_models",
                    "title": f"최신 오픈 LLM 추론 벤치마크 및 아키텍처 동향 ({current_date_str})",
                    "summary": "글로벌 AI 연구소들의 최신 추론 모델 경량화 및 멀티모달 컨텍스트 처리 기법이 활발히 공유되고 있습니다.",
                    "key_points": ["고난도 추론 최적화 프레임워크", "경량 온디바이스 에이전트 성능 향상"],
                    "source_name": "ArXiv & AI Research",
                    "source_url": "https://arxiv.org",
                    "tags": ["LLM", "Reasoning"]
                },
                {
                    "category_id": "ai_video",
                    "title": f"차세대 생성형 비디오 물리 시뮬레이션 및 모션 툴킷 ({current_date_str})",
                    "summary": "비디오 생성 AI에서 카메라 앵글 제어 및 피사체 일관성을 보장하는 기술이 고도화되고 있습니다.",
                    "key_points": ["고해상도 실시간 렌더링", "크리에이터 모션 제어 개선"],
                    "source_name": "TechCrunch AI",
                    "source_url": "https://techcrunch.com",
                    "tags": ["VideoGen", "CreativeAI"]
                },
                {
                    "category_id": "health_fitness",
                    "title": f"웨어러블 바이오마커와 운동생리학 기반 맞춤형 코칭 ({current_date_str})",
                    "summary": "수면, HRV, 대사 지표를 통합 분석하여 부상 방지 및 회복 가이드를 제공하는 헬스케어 AI 연구가 진전되고 있습니다.",
                    "key_points": ["생체 신호 기반 회복 지표", "개인 맞춤형 훈련 최적화"],
                    "source_name": "Nature Medicine",
                    "source_url": "https://www.nature.com",
                    "tags": ["Wearables", "Physiology"]
                }
            ]

    print(f"[Digest] Final today item count: {len(today_items)}")

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
    print(f"[Success] Successfully generated {index_file} ({len(html_output)} bytes)")

if __name__ == "__main__":
    main()
