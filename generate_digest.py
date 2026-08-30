import os
import sys
import json
import re
import datetime
from datetime import timezone, timedelta
import urllib.request
import urllib.error

# KST Timezone (UTC+9)
KST = timezone(timedelta(hours=9))

CATEGORIES = [
    {
        "id": "ai_models",
        "name": "AI Models & Architecture",
        "icon": "🤖",
        "badge_class": "bg-blue-500/10 text-blue-400 border border-blue-500/30",
        "dot_class": "bg-blue-400",
        "tier1_sources": "OpenAI, Anthropic, Google DeepMind, Qwen, DeepSeek official engineering blogs/news",
        "tier2_niche": "Hugging Face Daily Papers (upvoted papers), GitHub Trending AI repositories, Reddit r/LocalLLaMA quantization/reasoning tricks",
        "search_guidance": "1) Check for major model releases or weights in last 48h. 2) If few, expand to trending Hugging Face papers, clever open-source fine-tuning/reasoning tools, or GitHub AI gems."
    },
    {
        "id": "ai_video",
        "name": "AI Video & Creative Tech",
        "icon": "🎬",
        "badge_class": "bg-purple-500/10 text-purple-400 border border-purple-500/30",
        "dot_class": "bg-purple-400",
        "tier1_sources": "Kling AI, Higgsfield, Runway, Luma Dream Machine, Pika official changelogs",
        "tier2_niche": "Reddit r/comfyui custom nodes & workflows, r/aivideo creative experiments, open-source video diffusion & 3D Gaussian Splatting video tools",
        "search_guidance": "1) Check for major video generator updates. 2) If few, expand to trending ComfyUI video nodes, open-source motion control tools, or indie creator AI video techniques."
    },
    {
        "id": "health_fitness",
        "name": "Health & Fitness Tech",
        "icon": "🏃",
        "badge_class": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
        "dot_class": "bg-emerald-400",
        "tier1_sources": "Garmin firmware/sensor updates, Apple Health clinical news, Whoop, Oura",
        "tier2_niche": "Sports physiology & exercise science clinical studies (PubMed, Nature Medicine), metabolism/lactate/CGM experiments, indie wearable/biosensor projects, DC Rainmaker",
        "search_guidance": "1) Check for major wearable sensor firmware/releases. 2) If few, expand to fascinating sports science/exercise physiology research findings (HRV, lactate, recovery, fueling) or indie biosensors."
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

def extract_json_array_or_object(text):
    if not text:
        return None
    code_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.IGNORECASE)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except Exception:
            pass

    arr_match = re.search(r'(\[[\s\S]*\])', text)
    if arr_match:
        try:
            return json.loads(arr_match.group(1).strip())
        except Exception:
            pass

    obj_match = re.search(r'(\{[\s\S]*\})', text)
    if obj_match:
        try:
            return json.loads(obj_match.group(1).strip())
        except Exception:
            pass

    try:
        return json.loads(text.strip())
    except Exception:
        return None

def query_gemini_direct_rest(api_key, model_name, prompt, use_search=True):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3
        }
    }
    if use_search:
        payload["tools"] = [{"googleSearch": {}}]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            candidates = res_json.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join([p.get("text", "") for p in parts if "text" in p])
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"[REST API Error] {model_name} HTTP {e.code}: {err_msg[:250]}")
    except Exception as e:
        print(f"[REST API Error] {model_name}: {e}")
    return None

def query_gemini_with_sdk(api_key, model_name, prompt, use_search=True):
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=0.3)
        if use_search:
            config.tools = [types.Tool(google_search=types.GoogleSearch())]
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        if response and response.text:
            return response.text
    except Exception as e:
        print(f"[SDK Call Error] {model_name}: {e}")
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
        if ratio > 0.60:
            return True
    return False

def fetch_category_items(api_key, category, current_date_str, blacklist_titles):
    cat_id = category["id"]
    cat_name = category["name"]
    tier1_sources = category["tier1_sources"]
    tier2_niche = category["tier2_niche"]
    search_guidance = category["search_guidance"]

    blacklist_section = "\n".join(blacklist_titles[:15]) if blacklist_titles else "None"

    prompt = f"""You are a Principal Tech Analyst and Deep Tech Curator.
Current Date: {current_date_str} (KST)
Category: {cat_name} (ID: {cat_id})

2-TIER DISCOVERY STRATEGY:
1. Tier 1 (Major Breaking News):
   Sources: {tier1_sources}
   Look for official releases, benchmarks, architecture updates from the last 24-48 hours.

2. Tier 2 (Niche & Emerging Gems - IF major news is sparse):
   Sources: {tier2_niche}
   Look for high-signal community innovations, trending GitHub repositories, upvoted Hugging Face research papers, ComfyUI workflows, or fascinating sports science / physiological clinical experiments.

{search_guidance}

🚨 STRICT QUALITY & ANTI-MARKETING RULES:
- REJECT generic marketing slogans (e.g. "We build the next-gen AI").
- ADOPT ONLY items with concrete technical value (benchmarks, version changes, code/tools, clinical data, experimental findings).
- DEDUPLICATION: DO NOT repeat any of these recently covered stories:
{blacklist_section}

- Flexible Item Count: Return 2 to 4 high-quality items. If there are truly no worthy news items even in Tier 2, return an empty array `[]`.

URL REQUIREMENT:
`source_url` MUST be a deep direct link to the article, GitHub repo, paper, or release note.

JSON FORMAT:
Return ONLY a valid JSON array matching:
[
  {{
    "category_id": "{cat_id}",
    "type_badge": "🔥 Major Release" OR "💡 Research Insight" OR "🛠️ Open Source & Tool" OR "🧪 Science & Study",
    "title": "Specific, informative Korean headline",
    "summary": "2-3 sentences executive summary explaining technical mechanism, concrete metrics, and industry impact.",
    "key_points": [
      "Key technical metric / benchmark / architecture detail",
      "Concrete release feature / experimental finding"
    ],
    "source_name": "Specific source name (e.g., Anthropic Engineering, ArXiv, Hugging Face Papers, DC Rainmaker, PubMed)",
    "source_url": "https://...",
    "tags": ["Tag1", "Tag2"]
  }}
]
"""
    # Active Gemini Models
    models = ["gemini-3.6-flash", "gemini-3-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
    for model in models:
        text = query_gemini_with_sdk(api_key, model, prompt, use_search=True)
        if not text:
            text = query_gemini_direct_rest(api_key, model, prompt, use_search=True)
        if not text:
            text = query_gemini_direct_rest(api_key, model, prompt, use_search=False)

        if text:
            parsed = extract_json_array_or_object(text)
            items = []
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict) and "items" in parsed:
                items = parsed["items"]

            clean_items = []
            if items:
                for it in items:
                    title = it.get("title", "")
                    if len(title) > 5 and it.get("summary"):
                        clean_items.append(it)

            if len(clean_items) >= 1:
                print(f"[Success] Curated {len(clean_items)} items for '{cat_id}' via {model}")
                return clean_items

    print(f"[Warning] Live discovery returned 0 items for '{cat_id}'.")
    return []

def render_html_dashboard(current_date_str, today_items, past_digests):
    categorized_today = {c["id"]: [] for c in CATEGORIES}
    for item in today_items:
        cat_id = item.get("category_id", "ai_models")
        if cat_id in categorized_today:
            categorized_today[cat_id].append(item)
        else:
            categorized_today["ai_models"].append(item)

    today_cards_html = []
    total_today_count = len(today_items)

    for cat in CATEGORIES:
        cat_items = categorized_today[cat["id"]]
        
        if cat_items:
            for item in cat_items:
                title = item.get("title", "No Title")
                summary = item.get("summary", "")
                key_points = item.get("key_points", [])
                source_name = item.get("source_name", "Source")
                source_url = item.get("source_url", "#")
                type_badge = item.get("type_badge", "💡 Insight")
                tags = item.get("tags", [])

                tags_html = "".join([
                    f'<span class="inline-block text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 border border-slate-700/50">#{tag}</span>'
                    for tag in tags
                ])

                points_html = "".join([
                    f'<li class="flex items-start gap-2 text-xs sm:text-sm text-slate-300"><span class="text-sky-400 font-bold">▸</span><span>{point}</span></li>'
                    for point in key_points
                ])

                card = f"""
                <div class="digest-card group relative bg-slate-900/80 border border-slate-800/80 hover:border-slate-700/90 rounded-2xl p-4 sm:p-5 transition-all duration-200 backdrop-blur-sm flex flex-col justify-between" data-category="{cat['id']}">
                  <div>
                    <div class="flex items-center justify-between gap-2 mb-3">
                      <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold {cat['badge_class']}">
                          <span class="w-1.5 h-1.5 rounded-full {cat['dot_class']}"></span>
                          {cat['icon']} {cat['name']}
                        </span>
                        <span class="text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700/60 font-mono">{type_badge}</span>
                      </div>
                      <span class="text-[11px] text-slate-400 font-mono bg-slate-950/60 px-2 py-0.5 rounded-md border border-slate-800/50">{source_name}</span>
                    </div>

                    <h3 class="text-base sm:text-lg font-bold text-slate-100 group-hover:text-sky-300 transition-colors leading-snug mb-2.5">
                      {title}
                    </h3>

                    <p class="text-xs sm:text-sm text-slate-300 leading-relaxed mb-3">
                      {summary}
                    </p>

                    {f'<ul class="space-y-1.5 mb-4 bg-slate-950/60 p-3 rounded-xl border border-slate-800/60">{points_html}</ul>' if points_html else ''}
                  </div>

                  <div class="pt-3 border-t border-slate-800/60 flex items-center justify-between gap-2">
                    <div class="flex flex-wrap gap-1.5">
                      {tags_html}
                    </div>
                    <a href="{source_url}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-xs font-semibold text-sky-400 hover:text-sky-300 transition-colors shrink-0 bg-sky-500/10 px-2.5 py-1 rounded-lg border border-sky-500/20">
                      <span>심층 원문</span>
                      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                    </a>
                  </div>
                </div>
                """
                today_cards_html.append(card)
        else:
            empty_cat_card = f"""
            <div class="digest-card col-span-1 md:col-span-2 bg-slate-900/40 border border-dashed border-slate-800/80 rounded-2xl p-6 text-center transition-all flex flex-col items-center justify-center gap-2" data-category="{cat['id']}">
              <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold {cat['badge_class']} mb-1">
                {cat['icon']} {cat['name']}
              </div>
              <p class="text-sm font-semibold text-slate-300">☕ 오늘은 이 분야에 새로운 소식이 없습니다.</p>
              <p class="text-xs text-slate-500 max-w-sm">주요 릴리즈 및 틈새 연구 소식을 지속 모니터링 중입니다. 내일 다시 확인해 주세요.</p>
            </div>
            """
            today_cards_html.append(empty_cat_card)

    if total_today_count == 0:
        today_cards_rendered = f"""
        <div class="col-span-full bg-slate-900/50 border border-dashed border-slate-800/80 rounded-2xl p-8 sm:p-10 text-center flex flex-col items-center justify-center gap-3">
          <div class="text-3xl sm:text-4xl">☕</div>
          <h3 class="text-base sm:text-lg font-bold text-slate-200">오늘은 새로운 주요 소식이 없습니다</h3>
          <p class="text-xs sm:text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
            메이저 릴리즈 및 틈새 커뮤니티/논문 동향을 실시간 모니터링하고 있습니다. 내일 아침 08:30에 업데이트되는 새로운 브리핑을 확인해 주세요.
          </p>
        </div>
        """
    else:
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
                <a href="{i_url}" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 font-medium">원문 →</a>
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
          <span class="text-xs font-mono font-semibold tracking-wider uppercase text-sky-400">Deep Technical Briefing Engine</span>
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
        공식 엔지니어링 블로그, 오픈소스 리포지토리, 최신 연구 논문 기반 기술 브리핑을 매일 아침 전해드립니다.
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
        <span id="active-count" class="text-xs font-mono text-slate-400">{total_today_count} Items</span>
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
        const cardCat = card.getAttribute('data-category');
        if (catId === 'all' || cardCat === catId || card.classList.contains('col-span-full')) {{
          card.style.display = '';
          if (!card.textContent.includes('오늘은 새로운')) {{
            visibleCount++;
          }}
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
    print("[Pipeline] Starting Deep Technical Digest generator (with Tiered Discovery)...")
    current_date_str = get_current_kst_date()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    history_file = "history.json"
    index_file = "index.html"

    # 1. Load history & build strict blacklist
    history_data = load_history(history_file)
    pruned_digests, blacklist_titles, blacklist_set = prune_history_and_get_blacklist(history_data, current_date_str, max_days=7)
    print(f"[History] Retained {len(pruned_digests)} days of past history. Blacklisted items: {len(blacklist_titles)}")

    all_today_items = []

    # 2. Query each category with 2-Tier Discovery
    for cat in CATEGORIES:
        cat_id = cat["id"]
        print(f"\n[Category] Searching 2-Tier news for: {cat['name']} ({cat_id})...")
        
        items = []
        if api_key:
            items = fetch_category_items(api_key, cat, current_date_str, blacklist_titles)
        
        # Deduplication filtering
        valid_items = []
        if items:
            for it in items:
                t = it.get("title", "")
                if not is_duplicate_item(t, blacklist_set):
                    valid_items.append(it)
                else:
                    print(f"[Dedup] Skipped duplicate item: {t}")

        all_today_items.extend(valid_items)
        print(f"[Category] '{cat_id}' finalized with {len(valid_items)} articles.")

    print(f"\n[Digest] Total articles collected today: {len(all_today_items)}")

    # 3. Update history (only if we have items to record today)
    filtered_past = [d for d in pruned_digests if d.get("date") != current_date_str]
    if all_today_items:
        updated_digests = [{"date": current_date_str, "items": all_today_items}] + filtered_past
    else:
        updated_digests = filtered_past

    history_data_to_save = {
        "last_updated": datetime.datetime.now(KST).isoformat(),
        "digests": updated_digests
    }

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_data_to_save, f, ensure_ascii=False, indent=2)
    print(f"[Success] Saved updated history to {history_file}")

    # 4. Render index.html
    html_output = render_html_dashboard(current_date_str, all_today_items, updated_digests)

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"[Success] Successfully generated {index_file} ({len(html_output)} bytes)")

if __name__ == "__main__":
    main()
