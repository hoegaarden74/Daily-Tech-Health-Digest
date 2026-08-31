import os
import sys
import json
import re
import datetime
from datetime import timezone, timedelta
import urllib.request
import urllib.parse
import urllib.error

# KST Timezone (UTC+9)
KST = timezone(timedelta(hours=9))

CATEGORIES = [
    {
        "id": "ai_models",
        "name": "Applied AI Models & Tech",
        "icon": "🤖",
        "badge_class": "bg-blue-500/10 text-blue-400 border border-blue-500/30",
        "dot_class": "bg-blue-400",
        "target_sources": "Hugging Face Trend, GitHub Trending, Reddit (r/LocalLLaMA, r/MachineLearning), X Tech Community, Product Hunt, TechCrunch SaaS",
        "search_guidance": "Search for newly released/updated open-source weights, commercial API models, fine-tuning frameworks, and agentic infrastructure released or heavily discussed in the last 3 to 7 days. Focus strictly on models and tools with clear commercial applicability and developer adoption, excluding pure theoretical academic lab papers."
    },
    {
        "id": "ai_video",
        "name": "AI Content & Creator Tools",
        "icon": "🎬",
        "badge_class": "bg-purple-500/10 text-purple-400 border border-purple-500/30",
        "dot_class": "bg-purple-400",
        "target_sources": "Product Hunt, Reddit (r/StableDiffusion, r/AI_Agents, r/indiehackers), X AI Creators, Higgsfield, Kling AI, Runway, Luma, ComfyUI Eco, Toolify",
        "search_guidance": "Search for end-user commercial AI content creation tools, video generation SaaS (e.g., Higgsfield, Kling), avatar/voice generation, e-commerce marketing automation, and creator monetization platforms released or trending in the last 3 to 7 days. Focus on user workflows, practical use cases, and business models."
    },
    {
        "id": "health_fitness",
        "name": "Digital Health & Wellness Tech",
        "icon": "🏃",
        "badge_class": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
        "dot_class": "bg-emerald-400",
        "target_sources": "MobiHealthNews, DC Rainmaker, Gadgets & Wearables, Reddit (r/quantifiedself, r/Biohackers), Apple Health/Garmin Eco, Whoop, Oura, CGM SaaS Communities",
        "search_guidance": "Search for consumer digital health apps, wearable sensor integrations, continuous glucose monitoring (CGM) diet platforms, and AI personal coaching services gaining attention in the last 3 to 7 days. Focus on consumer UX, health data business models, and subscription monetization."
    }
]

CATEGORY_MAP = {c["id"]: c for c in CATEGORIES}

# 중복 판별 시 무시할 일반 테크 불용어 정의
GENERIC_STOPWORDS = {
    "ai", "saas", "app", "model", "platform", "tool", "tools", "generator", "agent", 
    "service", "system", "new", "the", "for", "with", "and", "via",
    "인공지능", "서비스", "플랫폼", "출시", "공개", "기술", "도구", "모델", "개발", "기반", "활용"
}

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
        except Exception:
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

def sanitize_and_resolve_url(raw_url, title, source_name, grounded_urls=None):
    clean_url = str(raw_url).strip() if raw_url else ""

    is_invalid = (
        not clean_url or
        clean_url == "#" or
        "..." in clean_url or
        "<" in clean_url or
        "example.com" in clean_url or
        "direct-link" in clean_url
    )

    if is_invalid:
        if grounded_urls and len(grounded_urls) > 0:
            return grounded_urls[0]
        q = f"{title} {source_name}"
        return f"https://www.google.com/search?q={urllib.parse.quote(q)}"

    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url

    return clean_url

def query_gemini_direct_rest(api_key, model_name, prompt, use_search=True):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2
        }
    }
    if use_search:
        payload["tools"] = [{"googleSearch": {}}]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=50) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            candidates = res_json.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join([p.get("text", "") for p in parts if "text" in p])
                
                grounded_urls = []
                g_meta = candidates[0].get("groundingMetadata", {})
                for chunk in g_meta.get("groundingChunks", []):
                    u = chunk.get("web", {}).get("uri")
                    if u:
                        grounded_urls.append(u)

                return text, grounded_urls
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"[REST API Error] {model_name} HTTP {e.code}: {err_msg[:200]}")
    except Exception as e:
        print(f"[REST API Error] {model_name}: {e}")
    return None, []

def query_gemini_with_sdk(api_key, model_name, prompt, use_search=True):
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=0.2)
        if use_search:
            config.tools = [types.Tool(google_search=types.GoogleSearch())]
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        if response and response.text:
            grounded_urls = []
            try:
                if response.candidates and len(response.candidates) > 0:
                    g_meta = getattr(response.candidates[0], "grounding_metadata", None)
                    if g_meta and hasattr(g_meta, "grounding_chunks"):
                        for chunk in g_meta.grounding_chunks:
                            if hasattr(chunk, "web") and hasattr(chunk.web, "uri"):
                                grounded_urls.append(chunk.web.uri)
            except Exception:
                pass
            return response.text, grounded_urls
    except Exception as e:
        print(f"[SDK Call Error] {model_name}: {e}")
    return None, []

def is_duplicate_item(item_title, blacklist_set):
    clean_title = item_title.strip().lower()
    if clean_title in blacklist_set:
        return True
    
    # 영문/한글 2글자 이상 토큰 추출 후 불용어 필터링
    raw_tokens = set(re.findall(r'[a-zA-Z0-9가-힣]{2,}', clean_title))
    item_tokens = {t for t in raw_tokens if t not in GENERIC_STOPWORDS}
    
    if len(item_tokens) < 2:
        return False
        
    for blacklisted in blacklist_set:
        b_raw = set(re.findall(r'[a-zA-Z0-9가-힣]{2,}', blacklisted))
        b_tokens = {t for t in b_raw if t not in GENERIC_STOPWORDS}
        if not b_tokens:
            continue
        overlap = len(item_tokens.intersection(b_tokens))
        union = len(item_tokens.union(b_tokens))
        jaccard = overlap / union if union > 0 else 0
        
        # 의미 있는 키워드 기준 유사도 70% 이상일 때만 중복으로 판별
        if jaccard >= 0.70:
            return True
    return False

def fetch_category_items(api_key, category, current_date_str, blacklist_titles):
    cat_id = category["id"]
    cat_name = category["name"]
    target_sources = category["target_sources"]
    search_guidance = category["search_guidance"]

    blacklist_section = "\n".join(blacklist_titles[:20]) if blacklist_titles else "None"

    prompt = f"""You are a Principal Product Strategist and Tech-to-Business Briefing Analyst.
Current Date: {current_date_str} (KST)
Category: {cat_name} (ID: {cat_id})

MISSION:
Search, curate, and structure 2 to 4 tangible product releases, applied AI models, creator SaaS solutions, or digital health platforms released or heavily discussed in the last 3 to 7 days.

TARGET CHANNELS & COMMUNITY SPACES:
- Key Domains: {target_sources}
- {search_guidance}
- Include signals from developer/creator communities (Reddit, Hacker News, X/Twitter, Product Hunt discussions) where practical utility is validated.

🚨 DEDUPLICATION (DO NOT REPEAT PREVIOUS HEADLINES):
{blacklist_section}

REQUIRED ITEM SCHEMA:
For each product/tool, provide concise analysis in Korean:
- "target_problem": 🎯 Target customer profile & specific pain point/problem being solved.
- "tech_applied": ⚙️ Core applied AI/model/hardware technology and workflow mechanics.
- "business_insight": 💼 Business model (SaaS subscription, usage-based, API), pricing, and strategic opportunity for founders.

CRITICAL URL RULE:
- Provide the real URL from your search results.
- If an exact article slug is not present, provide the official product homepage or service link.

OUTPUT FORMAT:
Return ONLY a valid JSON array of 2 to 4 items:
[
  {{
    "category_id": "{cat_id}",
    "type_badge": "🚀 New Product" OR "💼 B2B / SaaS" OR "📱 Consumer App" OR "💡 Use-Case & BM",
    "title": "명확하고 구체적인 국문 헤드라인",
    "target_problem": "타겟 고객 및 해결하려는 구체적 문제",
    "tech_applied": "적용된 기술 스택(LLM 모델명, 비전 인프라 등) 및 작동 방식",
    "business_insight": "수익 모델(구독, API 과금 등) 및 사업적 시사점",
    "source_name": "Source / Community name (e.g., Product Hunt, Reddit r/LocalLLaMA, TechCrunch)",
    "source_url": "https://exact-real-url...",
    "tags": ["AI", "SaaS", "Creator"]
  }}
]
"""
    # 안정적인 공식 모델 우선 호출
    models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    for model in models:
        text, grounded_urls = query_gemini_with_sdk(api_key, model, prompt, use_search=True)
        if not text:
            text, grounded_urls = query_gemini_direct_rest(api_key, model, prompt, use_search=True)

        if text:
            parsed = extract_json_array_or_object(text)
            items = []
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict) and "items" in parsed:
                items = parsed["items"]

            clean_items = []
            if items:
                for idx, it in enumerate(items):
                    title = it.get("title", "")
                    src_name = it.get("source_name", "Source")
                    raw_url = it.get("source_url", "")
                    
                    cand_grounded = grounded_urls[idx:idx+1] if grounded_urls and idx < len(grounded_urls) else grounded_urls
                    it["source_url"] = sanitize_and_resolve_url(raw_url, title, src_name, cand_grounded)

                    if len(title) > 3 and (it.get("target_problem") or it.get("summary") or it.get("tech_applied")):
                        clean_items.append(it)

            if len(clean_items) >= 1:
                print(f"[Success] Curated {len(clean_items)} verified items for '{cat_id}' via {model}")
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
                target_problem = item.get("target_problem", item.get("summary", ""))
                tech_applied = item.get("tech_applied", "")
                business_insight = item.get("business_insight", "")
                source_name = item.get("source_name", "Source")
                source_url = item.get("source_url", "#")
                type_badge = item.get("type_badge", "🚀 Product")
                tags = item.get("tags", [])

                tags_html = "".join([
                    f'<span class="inline-block text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 border border-slate-700/50">#{tag}</span>'
                    for tag in tags
                ])

                details_list = []
                if target_problem:
                    details_list.append(f'<li class="flex items-start gap-2 text-xs sm:text-sm text-slate-300"><span class="text-sky-400 font-semibold shrink-0">🎯 타겟/과제</span><span>{target_problem}</span></li>')
                if tech_applied:
                    details_list.append(f'<li class="flex items-start gap-2 text-xs sm:text-sm text-slate-300"><span class="text-indigo-400 font-semibold shrink-0">⚙️ 적용 기술</span><span>{tech_applied}</span></li>')
                if business_insight:
                    details_list.append(f'<li class="flex items-start gap-2 text-xs sm:text-sm text-emerald-300"><span class="text-emerald-400 font-semibold shrink-0">💼 BM/시사점</span><span>{business_insight}</span></li>')

                points_html = "".join(details_list)

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

                    <h3 class="text-base sm:text-lg font-bold text-slate-100 group-hover:text-sky-300 transition-colors leading-snug mb-3">
                      {title}
                    </h3>

                    {f'<ul class="space-y-2 mb-4 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/60">{points_html}</ul>' if points_html else ''}
                  </div>

                  <div class="pt-3 border-t border-slate-800/60 flex items-center justify-between gap-2">
                    <div class="flex flex-wrap gap-1.5">
                      {tags_html}
                    </div>
                    <a href="{source_url}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-xs font-semibold text-sky-400 hover:text-sky-300 transition-colors shrink-0 bg-sky-500/10 px-2.5 py-1 rounded-lg border border-sky-500/20">
                      <span>서비스/원문 보기</span>
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
              <p class="text-sm font-semibold text-slate-300">☕ 해당 카테고리에 등록된 신규 솔루션 소식이 없습니다.</p>
              <p class="text-xs text-slate-500 max-w-sm">실용적인 서비스 릴리즈 및 비즈니스 유스케이스를 지속 모니터링 중입니다.</p>
            </div>
            """
            today_cards_html.append(empty_cat_card)

    if total_today_count == 0:
        today_cards_rendered = f"""
        <div class="col-span-full bg-slate-900/50 border border-dashed border-slate-800/80 rounded-2xl p-8 sm:p-10 text-center flex flex-col items-center justify-center gap-3">
          <div class="text-3xl sm:text-4xl">☕</div>
          <h3 class="text-base sm:text-lg font-bold text-slate-200">오늘은 새로운 비즈니스/제품 소식이 없습니다</h3>
          <p class="text-xs sm:text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
            실사용 가치가 높은 신규 서비스 릴리즈 및 비즈니스 활용 사례를 지속적으로 모니터링하고 있습니다.
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
                <a href="{i_url}" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 font-medium">서비스 →</a>
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

    archive_rendered = "\n".join(archive_days_html) if archive_days_html else """
    <div class="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-6 text-center text-slate-500 text-sm">
      과거 7일간의 누적 헤드라인 아카이브가 이곳에 순차적으로 보관됩니다.
    </div>
    """

    html_content = f"""<!DOCTYPE html>
<html lang="ko" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Daily Tech & Product Briefing</title>
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
          <span class="text-xs font-mono font-semibold tracking-wider uppercase text-sky-400">Tech-to-Business Intelligence</span>
        </div>
        <div class="inline-flex items-center justify-center gap-2 text-xs font-mono text-slate-400 bg-slate-900/80 border border-slate-800/80 px-3 py-1 rounded-full">
          <span>KST {current_date_str}</span>
          <span class="text-slate-600">|</span>
          <span class="text-emerald-400">Live Active</span>
        </div>
      </div>

      <h1 class="text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-white mb-2">
        Daily Tech & Product Briefing
      </h1>
      <p class="text-xs sm:text-sm text-slate-400 max-w-2xl leading-relaxed">
        실전 AI 모델, 크리에이터 제작 툴, 디지털 헬스케어의 최신 출시 소식과 비즈니스 활용 사례를 전달합니다.
      </p>

      <div class="mt-5 flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none">
        <button onclick="filterCategory('all')" id="tab-all" class="filter-tab px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-sky-500 text-white shadow-sm transition-all shrink-0">
          전체 보기
        </button>
        <button onclick="filterCategory('ai_models')" id="tab-ai_models" class="filter-tab px-3.5 py-1.5 rounded-xl text-xs font-medium bg-slate-900/90 text-slate-300 border border-slate-800 hover:border-slate-700 transition-all shrink-0">
          🤖 AI Models & Tech
        </button>
        <button onclick="filterCategory('ai_video')" id="tab-ai_video" class="filter-tab px-3.5 py-1.5 rounded-xl text-xs font-medium bg-slate-900/90 text-slate-300 border border-slate-800 hover:border-slate-700 transition-all shrink-0">
          🎬 AI Content & Tools
        </button>
        <button onclick="filterCategory('health_fitness')" id="tab-health_fitness" class="filter-tab px-3.5 py-1.5 rounded-xl text-xs font-medium bg-slate-900/90 text-slate-300 border border-slate-800 hover:border-slate-700 transition-all shrink-0">
          🏃 Digital Health & Tech
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
        <span class="text-xs text-slate-500 font-mono">7-Day Buffer</span>
      </div>

      <div class="space-y-3">
        {archive_rendered}
      </div>
    </section>

    <footer class="mt-10 py-6 border-t border-slate-900 text-center text-xs text-slate-500 space-y-2">
      <p>Automated by <strong>GitHub Actions</strong> & <strong>Google GenAI Engine</strong></p>
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
          if (!card.textContent.includes('해당 카테고리에 등록된')) {{
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
    print("[Pipeline] Starting Tech-to-Business Briefing generator...")
    current_date_str = get_current_kst_date()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    history_file = "history.json"
    index_file = "index.html"

    # 1. 과거 히스토리 로드 및 중복 방지 리스트 구성
    history_data = load_history(history_file)
    pruned_digests, blacklist_titles, blacklist_set = prune_history_and_get_blacklist(history_data, current_date_str, max_days=7)
    print(f"[History] Retained {len(pruned_digests)} days of past history. Blacklisted items: {len(blacklist_titles)}")

    all_today_items = []

    # 2. 카테고리별 데이터 큐레이션 실행
    for cat in CATEGORIES:
        cat_id = cat["id"]
        print(f"\n[Category] Searching practical products/services for: {cat['name']} ({cat_id})...")
        
        items = []
        if api_key:
            items = fetch_category_items(api_key, cat, current_date_str, blacklist_titles)
        
        # 고유명사 기반 중복 필터링
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

    print(f"\n[Digest] Total items collected today: {len(all_today_items)}")

    # 3. 히스토리 갱신
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

    # 4. HTML 파일 렌더링
    html_output = render_html_dashboard(current_date_str, all_today_items, updated_digests)

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"[Success] Successfully generated {index_file} ({len(html_output)} bytes)")

if __name__ == "__main__":
    main()
