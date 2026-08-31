import os
import sys
import json
import re
import time
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
        "search_guidance": "실제 상용화 가능한 AI 오픈가중치 모델, 신규 상용 API 모델, 파인튜닝/에이전트 인프라. 순수 이론 논문 배제."
    },
    {
        "id": "ai_video",
        "name": "AI Content & Creator Tools",
        "icon": "🎬",
        "badge_class": "bg-purple-500/10 text-purple-400 border border-purple-500/30",
        "dot_class": "bg-purple-400",
        "target_sources": "Product Hunt, Reddit (r/StableDiffusion, r/AI_Agents, r/indiehackers), X AI Creators, Higgsfield, Kling AI, Runway, Luma, ComfyUI Eco, Toolify",
        "search_guidance": "엔드유저용 상용 생성형 AI 솔루션, 비디오 생성 SaaS(Higgsfield 등), 아바타/보이스 솔루션, 마케팅 자동화 및 크리에이터 BM 툴."
    },
    {
        "id": "health_fitness",
        "name": "Digital Health & Wellness Tech",
        "icon": "🏃",
        "badge_class": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
        "dot_class": "bg-emerald-400",
        "target_sources": "MobiHealthNews, DC Rainmaker, Gadgets & Wearables, Reddit (r/quantifiedself, r/Biohackers), Apple Health/Garmin Eco, Whoop, Oura, CGM SaaS Communities",
        "search_guidance": "소비자용 디지털 헬스케어 앱, 웨어러블 센서 바이오데이터 연동, CGM 기반 다이어트/피트니스, AI 맞춤형 코칭 BM."
    }
]

CATEGORY_MAP = {c["id"]: c for c in CATEGORIES}

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

def query_gemini_unified(api_key, model_name, prompt, use_search=True):
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
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
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
            if e.code == 429:
                print(f"[Rate Limit] 429 Quota Exceeded. 10초 대기 후 재시도합니다 (시도 {attempt+1}/{max_retries})...")
                time.sleep(10)
                continue
            print(f"[REST API Error] {model_name} (Search={use_search}) HTTP {e.code}: {err_msg[:200]}")
            break
        except Exception as e:
            print(f"[REST API Error] {model_name} (Search={use_search}): {e}")
            break
    return None, []

def is_duplicate_item(item_title, blacklist_set):
    clean_title = item_title.strip().lower()
    if clean_title in blacklist_set:
        return True
    
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
        
        if jaccard >= 0.70:
            return True
    return False

def fetch_all_categories_unified(api_key, current_date_str, blacklist_titles):
    blacklist_section = "\n".join(blacklist_titles[:25]) if blacklist_titles else "None"

    cat_descriptions = []
    for cat in CATEGORIES:
        desc = f"- Category ID: \"{cat['id']}\" ({cat['name']})\n  Target Sources: {cat['target_sources']}\n  Focus: {cat['search_guidance']}"
        cat_descriptions.append(desc)

    categories_prompt_block = "\n\n".join(cat_descriptions)

    prompt = f"""You are a Principal Product Strategist and Tech-to-Business Briefing Analyst.
Current Date: {current_date_str} (KST)

MISSION:
Perform a single comprehensive web search and curate 2 to 3 practical, high-value product launches, applied AI tools, or digital health services for EACH of the following 3 categories (Total 6 to 9 items):

{categories_prompt_block}

CRITICAL RULES:
1. Search recent 3 to 7 days of announcements, releases, and community discussions (Reddit, Product Hunt, X, Hacker News).
2. Focus strictly on commercial viability, business models, and end-user solutions. Exclude pure theoretical math or laboratory papers.
3. Provide real, exact URLs from your search results.

🚨 DEDUPLICATION (DO NOT REPEAT RECENT STORIES):
{blacklist_section}

OUTPUT FORMAT:
Return ONLY a valid JSON array containing items for ALL 3 categories:
[
  {{
    "category_id": "ai_models" | "ai_video" | "health_fitness",
    "type_badge": "🚀 New Product" | "💼 B2B / SaaS" | "📱 Consumer App" | "💡 Use-Case & BM",
    "title": "명확하고 구체적인 국문 헤드라인",
    "target_problem": "🎯 타겟 고객 및 해결하려는 구체적 문제점",
    "tech_applied": "⚙️ 적용 기술 스택(LLM 모델명, 센서 연동 등) 및 구현 방식",
    "business_insight": "💼 수익/과금 모델(구독, API 등) 및 사업적 시사점",
    "source_name": "Source / Community name",
    "source_url": "https://exact-real-url...",
    "tags": ["AI", "SaaS", "Creator"]
  }}
]
"""
    model = "gemini-3.6-flash"
    print(f"[Pipeline] Requesting unified 3-category curation via {model} (Single Batch Request)...")

    # 1. 단일 Search Grounding 호출
    text, grounded_urls = query_gemini_unified(api_key, model, prompt, use_search=True)

    # 2. Search Grounding 실패 시 일반 텍스트 모드로 우회 (Fallback)
    if not text:
        print(f"[Fallback] Search 일시 제한으로 {model} 표준 생성 모드로 전환합니다.")
        time.sleep(3)
        text, grounded_urls = query_gemini_unified(api_key, model, prompt, use_search=False)

    if text:
        parsed = extract_json_array_or_object(text)
        items = []
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            for k in ["items", "data", "results"]:
                if k in parsed and isinstance(parsed[k], list):
                    items = parsed[k]
                    break

        clean_items = []
        if items:
            for idx, it in enumerate(items):
                title = it.get("title", "")
                cat_id = it.get("category_id", "")
                src_name = it.get("source_name", "Source")
                raw_url = it.get("source_url", "")
                
                if cat_id not in CATEGORY_MAP:
                    continue

                cand_grounded = grounded_urls[idx:idx+1] if grounded_urls and idx < len(grounded_urls) else grounded_urls
                it["source_url"] = sanitize_and_resolve_url(raw_url, title, src_name, cand_grounded)

                if len(title) > 3 and (it.get("target_problem") or it.get("summary") or it.get("tech_applied")):
                    clean_items.append(it)

        if clean_items:
            print(f"[Success] Unified curation succeeded with {len(clean_items)} verified items.")
            return clean_items

    print("[Warning] Unified curation returned 0 items.")
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
                      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke_linecap="round" stroke_linejoin="round" stroke_width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
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

    if not api_key:
        print("[CRITICAL ERROR] GEMINI_API_KEY 환경 변수가 비어 있습니다.")
        sys.exit(1)

    history_file = "history.json"
    index_file = "index.html"

    # 1. 히스토리 로드 및 중복 리스트 추출
    history_data = load_history(history_file)
    pruned_digests, blacklist_titles, blacklist_set = prune_history_and_get_blacklist(history_data, current_date_str, max_days=7)
    print(f"[History] Retained {len(pruned_digests)} days of past history. Blacklisted items: {len(blacklist_titles)}")

    # 2. 3개 카테고리 단일 통합 큐레이션 실행 (단 1회 호출)
    raw_items = fetch_all_categories_unified(api_key, current_date_str, blacklist_titles)

    # 3. 중복 필터링 적용
    all_today_items = []
    if raw_items:
        for it in raw_items:
            t = it.get("title", "")
            if not is_duplicate_item(t, blacklist_set):
                all_today_items.append(it)
            else:
                print(f"[Dedup] Skipped duplicate item: {t}")

    print(f"\n[Digest] Total items collected today: {len(all_today_items)}")

    # 4. 히스토리 저장
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

    # 5. HTML 파일 렌더링
    html_output = render_html_dashboard(current_date_str, all_today_items, updated_digests)

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"[Success] Successfully generated {index_file} ({len(html_output)} bytes)")

if __name__ == "__main__":
    main()
