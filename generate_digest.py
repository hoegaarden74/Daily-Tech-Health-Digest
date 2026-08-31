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

def query_gemini_strict_grounded(api_key, model_name, prompt):
    """
    실시간 구글 검색(Google Search Tool)을 필수 강제하는 단일 호출 함수.
    비검색 모드로의 Fallback을 완전히 차단함.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,  # 임의 생성(환각) 방지를 위해 온도를 0.1로 엄격히 고정
            "responseMimeType": "application/json"
        },
        "tools": [{"googleSearch": {}}]
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    max_retries = 3
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
                wait_sec = 20 * (attempt + 1)
                print(f"[Rate Limit] 429 Quota Exceeded. {wait_sec}초 쿨다운 대기 (시도 {attempt+1}/{max_retries})...")
                time.sleep(wait_sec)
                continue
            print(f"[REST API Error] {model_name} HTTP {e.code}: {err_msg[:250]}")
            break
        except Exception as e:
            print(f"[REST API Error] {model_name}: {e}")
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

def fetch_strict_verified_briefing_and_radar(api_key, current_date_str, blacklist_titles):
    blacklist_section = "\n".join(blacklist_titles[:25]) if blacklist_titles else "None"

    cat_descriptions = []
    for cat in CATEGORIES:
        desc = f"- Category ID: \"{cat['id']}\" ({cat['name']})\n  Target Sources: {cat['target_sources']}\n  Focus: {cat['search_guidance']}"
        cat_descriptions.append(desc)

    categories_prompt_block = "\n\n".join(cat_descriptions)

    prompt = f"""You are a Principal Product Strategist and Tech Briefing Engine with a STRICT ZERO-HALLUCINATION POLICY.
Current Date: {current_date_str} (KST)

MANDATORY RULES:
1. You MUST ONLY extract news, products, and updates from the live Google Search grounding results.
2. NEVER invent, synthesize, hallucinate, or imagine hypothetical products, services, scenarios, or fictional names.
3. If no actual product launch or verified news is found for a category in the recent 3 to 7 days, return an EMPTY ARRAY for that category.
4. "source_url" MUST be the actual article or real product URL found in search results.

TASK 1: BUSINESS BRIEFING ITEMS (2 to 3 real products per category)
{categories_prompt_block}

TASK 2: LLM STATS & MODEL RELEASE RADAR (3 to 5 real releases and benchmark updates)
Direct Target References:
- https://llm-stats.com/ai-news
- https://llm-stats.com/llm-updates
Search recent model version updates, open-weight releases, API pricing shifts, and benchmark leaderboards.

DEDUPLICATION (DO NOT REPEAT):
{blacklist_section}

OUTPUT STRICT JSON SCHEMA (No markdown, JSON only):
{{
  "briefing_items": [
    {{
      "category_id": "ai_models" | "ai_video" | "health_fitness",
      "type_badge": "🚀 New Product" | "💼 B2B / SaaS" | "📱 Consumer App" | "💡 Use-Case & BM",
      "title": "실존하는 제품/서비스의 국문 헤드라인",
      "target_problem": "실제 해결하는 구체적 문제",
      "tech_applied": "실제 적용된 기술 스택 및 구현 방식",
      "business_insight": "실제 과금 모델(구독, API 등) 및 사업적 시사점",
      "source_name": "실제 출처명",
      "source_url": "https://실제-검증된-URL",
      "tags": ["AI", "SaaS"]
    }}
  ],
  "llm_radar_items": [
    {{
      "badge": "🚀 Model Release" | "📊 Benchmark" | "⚡ API & Infra",
      "title": "실제 출시된 모델명 및 업데이트 요약",
      "org": "출시 기관/기업명",
      "summary": "핵심 스펙, 벤치마크 점수 및 변경사항",
      "source_name": "LLM Stats",
      "source_url": "https://llm-stats.com/ai-news"
    }}
  ]
}}
"""
    model = "gemini-3.6-flash"
    print(f"[Pipeline] Executing Strict Grounded Search via {model}...")

    text, grounded_urls = query_gemini_strict_grounded(api_key, model, prompt)

    if not text:
        print("[Warning] Real-time Search Grounding failed or was rate-limited. Returning 0 items to prevent hallucination.")
        return [], []

    briefing_items = []
    llm_radar_items = []

    parsed = extract_json_array_or_object(text)
    if isinstance(parsed, dict):
        raw_briefings = parsed.get("briefing_items", [])
        raw_radars = parsed.get("llm_radar_items", [])

        # Briefing validation
        for it in raw_briefings:
            title = it.get("title", "").strip()
            cat_id = it.get("category_id", "").strip()
            src_url = it.get("source_url", "").strip()

            if cat_id not in CATEGORY_MAP:
                continue

            # 유효 URL 기본 검증 (더미 링크, 비정상 링크 배제)
            if not src_url or src_url == "#" or "example.com" in src_url:
                continue

            if len(title) > 3 and (it.get("target_problem") or it.get("summary") or it.get("tech_applied")):
                briefing_items.append(it)

        # Radar validation
        for it in raw_radars:
            r_title = it.get("title", "").strip()
            if len(r_title) > 2:
                llm_radar_items.append(it)

    print(f"[Success] Verified {len(briefing_items)} real briefings & {len(llm_radar_items)} real radar items.")
    return briefing_items, llm_radar_items

def render_html_dashboard(current_date_str, today_items, past_digests, llm_radar_items=None):
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
              <p class="text-sm font-semibold text-slate-300">☕ 해당 카테고리에 검증된 신규 상용 솔루션 소식이 없습니다.</p>
              <p class="text-xs text-slate-500 max-w-sm">실사용 가치가 높은 실시간 릴리즈를 실시간 모니터링 중입니다.</p>
            </div>
            """
            today_cards_html.append(empty_cat_card)

    if total_today_count == 0:
        today_cards_rendered = f"""
        <div class="col-span-full bg-slate-900/50 border border-dashed border-slate-800/80 rounded-2xl p-8 sm:p-10 text-center flex flex-col items-center justify-center gap-3">
          <div class="text-3xl sm:text-4xl">☕</div>
          <h3 class="text-base sm:text-lg font-bold text-slate-200">오늘은 검증된 신규 비즈니스 소식이 없습니다</h3>
          <p class="text-xs sm:text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
            인터넷 상의 미확인 추론 데이터를 배제하고, 실시간 검색으로 검증된 실제 릴리즈만 수집합니다.
          </p>
        </div>
        """
    else:
        today_cards_rendered = "\n".join(today_cards_html)

    radar_cards_html = []
    if llm_radar_items:
        for r_item in llm_radar_items:
            r_badge = r_item.get("badge", "🚀 Model Release")
            r_title = r_item.get("title", "")
            r_org = r_item.get("org", "AI Lab")
            r_sum = r_item.get("summary", "")
            r_url = r_item.get("source_url", "https://llm-stats.com/ai-news")

            badge_color = "bg-amber-500/10 text-amber-300 border-amber-500/30" if "Release" in r_badge else "bg-cyan-500/10 text-cyan-300 border-cyan-500/30"

            r_card = f"""
            <div class="bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-xl p-3.5 transition-all flex flex-col justify-between">
              <div>
                <div class="flex items-center justify-between gap-2 mb-2">
                  <span class="text-[11px] font-semibold px-2 py-0.5 rounded-md border {badge_color}">{r_badge}</span>
                  <span class="text-[11px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800/60">{r_org}</span>
                </div>
                <h4 class="text-sm font-bold text-slate-100 hover:text-amber-300 transition-colors mb-1.5">{r_title}</h4>
                <p class="text-xs text-slate-400 leading-relaxed mb-3">{r_sum}</p>
              </div>
              <div class="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
                <span class="text-slate-500 font-mono">Source: LLM-Stats.com</span>
                <a href="{r_url}" target="_blank" rel="noopener noreferrer" class="text-amber-400 hover:text-amber-300 font-medium">스펙/벤치마크 확인 →</a>
              </div>
            </div>
            """
            radar_cards_html.append(r_card)
        radar_rendered = f"""
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {"".join(radar_cards_html)}
        </div>
        """
    else:
        radar_rendered = """
        <div class="bg-slate-900/40 border border-dashed border-slate-800 rounded-xl p-4 text-center text-xs text-slate-500">
          검증된 실시간 모델 릴리즈 피드가 없습니다.
        </div>
        """

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
          <span class="text-xs font-mono font-semibold tracking-wider uppercase text-sky-400">Verified Tech Intelligence</span>
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
        실전 AI 모델, 크리에이터 제작 툴, 디지털 헬스케어의 실시간 검증된 릴리즈 소식과 비즈니스 활용 사례를 전달합니다.
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

    <!-- SECTION 1: TODAY'S CURATED BRIEFING -->
    <main class="space-y-4 mb-8">
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

    <!-- SECTION 2: LLM STATS LIVE RADAR -->
    <section class="mb-10 bg-slate-950/70 border border-slate-800/90 rounded-2xl p-4 sm:p-5">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4 pb-3 border-b border-slate-800/80">
        <div>
          <h3 class="text-base font-bold text-slate-100 flex items-center gap-2">
            <span class="text-amber-400">📡</span> LLM Stats Live Radar
            <span class="text-[11px] font-mono font-normal text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">llm-stats.com Live</span>
          </h3>
          <p class="text-xs text-slate-400 mt-0.5">글로벌 AI 연구소의 실시간 모델 출시, API 변경 및 벤치마크 업데이트 현황입니다.</p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <a href="https://llm-stats.com/ai-news" target="_blank" rel="noopener noreferrer" class="text-[11px] font-mono text-sky-400 hover:underline">AI News ↗</a>
          <span class="text-slate-700">•</span>
          <a href="https://llm-stats.com/llm-updates" target="_blank" rel="noopener noreferrer" class="text-[11px] font-mono text-sky-400 hover:underline">Model Updates ↗</a>
        </div>
      </div>
      {radar_rendered}
    </section>

    <!-- SECTION 3: WEEKLY ARCHIVE -->
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
      <p>Automated by <strong>GitHub Actions</strong> & <strong>Google GenAI Grounding Engine</strong></p>
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
          if (!card.textContent.includes('해당 카테고리에 검증된') && !card.textContent.includes('오늘은 검증된')) {{
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
    print("[Pipeline] Starting Strict Verified Briefing & LLM-Stats Radar generator...")
    current_date_str = get_current_kst_date()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        print("[CRITICAL ERROR] GEMINI_API_KEY 환경 변수가 비어 있습니다.")
        sys.exit(1)

    history_file = "history.json"
    index_file = "index.html"

    history_data = load_history(history_file)
    pruned_digests, blacklist_titles, blacklist_set = prune_history_and_get_blacklist(history_data, current_date_str, max_days=7)
    print(f"[History] Retained {len(pruned_digests)} days of past history. Blacklisted items: {len(blacklist_titles)}")

    raw_briefings, llm_radar_items = fetch_strict_verified_briefing_and_radar(api_key, current_date_str, blacklist_titles)

    all_today_items = []
    if raw_briefings:
        for it in raw_briefings:
            t = it.get("title", "")
            if not is_duplicate_item(t, blacklist_set):
                all_today_items.append(it)
            else:
                print(f"[Dedup] Skipped duplicate item: {t}")

    print(f"\n[Digest] Total verified briefings: {len(all_today_items)}, Radar items: {len(llm_radar_items)}")

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

    html_output = render_html_dashboard(current_date_str, all_today_items, updated_digests, llm_radar_items)

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"[Success] Successfully generated {index_file} ({len(html_output)} bytes)")

if __name__ == "__main__":
    main()
