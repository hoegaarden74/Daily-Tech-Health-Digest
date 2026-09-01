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
import xml.etree.ElementTree as ET

# KST Timezone (UTC+9)
KST = timezone(timedelta(hours=9))

CATEGORIES = [
    {
        "id": "ai_models",
        "name": "Applied AI Models & Tech",
        "icon": "🤖",
        "badge_class": "bg-blue-500/10 text-blue-400 border border-blue-500/30",
        "dot_class": "bg-blue-400",
        "sources": [
            {"type": "rss", "name": "MarkTechPost", "url": "https://www.marktechpost.com/category/technology/artificial-intelligence/feed/"},
            {"type": "rss", "name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml"},
            {"type": "web", "name": "AlphaSignal", "url": "https://alphasignal.ai/"}
        ]
    },
    {
        "id": "ai_video",
        "name": "AI Content & Creator Tools",
        "icon": "🎬",
        "badge_class": "bg-purple-500/10 text-purple-400 border border-purple-500/30",
        "dot_class": "bg-purple-400",
        "sources": [
            {"type": "rss", "name": "Reddit r/StableDiffusion", "url": "https://www.reddit.com/r/StableDiffusion/top/.rss?t=day"},
            {"type": "rss", "name": "Product Hunt AI", "url": "https://www.producthunt.com/feed"},
            {"type": "rss", "name": "The Rundown AI", "url": "https://www.therundown.ai/feed"},
            {"type": "web", "name": "TLDR AI", "url": "https://tldr.tech/ai"},
            {"type": "web", "name": "Ben's Bites", "url": "https://www.bensbites.com/"}
        ]
    },
    {
        "id": "health_fitness",
        "name": "Digital Health & Wellness Tech",
        "icon": "🏃",
        "badge_class": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
        "dot_class": "bg-emerald-400",
        "sources": [
            {"type": "rss", "name": "Gadgets & Wearables", "url": "https://gadgetsandwearables.com/feed/"},
            {"type": "rss", "name": "DC Rainmaker", "url": "https://www.dcrainmaker.com/feed"}
        ]
    }
]

CATEGORY_MAP = {c["id"]: c for c in CATEGORIES}

RADAR_SOURCES = [
    {"name": "LLM-Stats Updates", "url": "https://llm-stats.com/llm-updates"},
    {"name": "LLM-Stats AI News", "url": "https://llm-stats.com/ai-news"},
    {"name": "Artificial Analysis", "url": "https://artificialanalysis.ai/"}
]

FALLBACK_MODELS = [
    "gemini-3.6-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (DailyDigest/3.5)"
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

def prune_history(history_data, current_date_str, max_days=7):
    current_dt = datetime.datetime.strptime(current_date_str, "%Y-%m-%d").date()
    pruned_digests = []

    for digest in history_data.get("digests", []):
        d_str = digest.get("date")
        if not d_str:
            continue
        try:
            d_dt = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            diff_days = (current_dt - d_dt).days
            if 0 <= diff_days < max_days:
                pruned_digests.append(digest)
        except Exception:
            continue

    pruned_digests.sort(key=lambda x: x.get("date", ""), reverse=True)
    return pruned_digests

def fetch_rss_feed(source_name, feed_url, max_items=4):
    """RSS 2.0 및 Atom 규격을 동시 지원하는 XML 파서"""
    articles = []
    req = urllib.request.Request(feed_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            xml_data = resp.read()
            root = ET.fromstring(xml_data)

            # 1. RSS 2.0 처리
            items = root.findall(".//item")
            if items:
                for item in items[:max_items]:
                    t = item.findtext("title", "").strip()
                    l = item.findtext("link", "").strip()
                    d = item.findtext("description", "").strip()
                    clean_d = re.sub(r"<[^>]+>", " ", d)[:300].strip()
                    if t and l:
                        articles.append({
                            "source_name": source_name,
                            "title": t,
                            "url": l,
                            "summary": clean_d if clean_d else t
                        })
                return articles

            # 2. Atom 처리 (Reddit, Hugging Face 등)
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
            for entry in entries[:max_items]:
                t, l, d = "", "", ""
                for child in entry:
                    tag_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag_name == "title":
                        t = (child.text or "").strip()
                    elif tag_name == "link":
                        l = child.attrib.get("href", "").strip() or (child.text or "").strip()
                    elif tag_name in ["summary", "content"]:
                        d = (child.text or "").strip()

                clean_d = re.sub(r"<[^>]+>", " ", d)[:300].strip()
                if t and l:
                    articles.append({
                        "source_name": source_name,
                        "title": t,
                        "url": l,
                        "summary": clean_d if clean_d else t
                    })
    except Exception as e:
        print(f"[RSS Error] {source_name} ({feed_url}): {e}")
    return articles

def fetch_web_snippet(source_name, target_url, max_chars=1200):
    """HTML 페이지에서 노이즈 태그를 정제하고 텍스트 스니펫 추출"""
    articles = []
    req = urllib.request.Request(target_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            text_clean = re.sub(r"<script[\s\S]*?</script>", "", html)
            text_clean = re.sub(r"<style[\s\S]*?</style>", "", text_clean)
            text_clean = re.sub(r"<nav[\s\S]*?</nav>", "", text_clean)
            text_clean = re.sub(r"<footer[\s\S]*?</footer>", "", text_clean)
            text_clean = re.sub(r"<[^>]+>", " ", text_clean)
            text_clean = re.sub(r"\s+", " ", text_clean)[:max_chars].strip()

            if len(text_clean) > 50:
                articles.append({
                    "source_name": source_name,
                    "title": f"{source_name} Latest Intelligence",
                    "url": target_url,
                    "summary": text_clean
                })
    except Exception as e:
        print(f"[Web Scrape Error] {source_name} ({target_url}): {e}")
    return articles

def deduplicate_raw_items(items):
    """URL 및 제목 유사도 기준 1차 중복 제거"""
    seen_titles = set()
    unique_items = []
    for it in items:
        # 영문/숫자 기준 20글자 정규화 키 생성
        norm_key = re.sub(r"[^a-zA-Z0-9가-힣]", "", it.get("title", ""))[:25].lower()
        if norm_key and norm_key not in seen_titles:
            seen_titles.add(norm_key)
            unique_items.append(it)
    return unique_items

def fetch_radar_data():
    """LLM-Stats 및 Artificial Analysis 정량 벤치마크/릴리즈 수집"""
    radar_raw = []
    for r_src in RADAR_SOURCES:
        req = urllib.request.Request(r_src["url"], headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                text_clean = re.sub(r"<script[\s\S]*?</script>", "", html)
                text_clean = re.sub(r"<style[\s\S]*?</style>", "", text_clean)
                text_clean = re.sub(r"<[^>]+>", " ", text_clean)
                text_clean = re.sub(r"\s+", " ", text_clean)[:1000].strip()

                radar_raw.append({
                    "source_name": r_src["name"],
                    "url": r_src["url"],
                    "content_snippet": text_clean
                })
        except Exception as e:
            print(f"[Radar Fetch Error] {r_src['name']}: {e}")
            radar_raw.append({
                "source_name": r_src["name"],
                "url": r_src["url"],
                "content_snippet": "Latest LLM model releases, benchmark scores, quality vs cost indicators."
            })
    return radar_raw

def query_gemini_waterfall(api_key, prompt):
    """우선순위 모델 순차 우회 (Waterfall Fallback)"""
    for model_name in FALLBACK_MODELS:
        print(f"[Pipeline] Requesting structured analysis via model: {model_name}...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode("utf-8")
                res_json = json.loads(body)
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join([p.get("text", "") for p in parts if "text" in p])
                    if text:
                        print(f"[Success] Successfully generated brief via {model_name}")
                        return text, model_name
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            print(f"[Model Fail] {model_name} HTTP {e.code}: {err_msg[:160]}")
            print(f"[Fallback] Switching to next fallback model...")
            time.sleep(2)
        except Exception as e:
            print(f"[Model Fail] {model_name} Error: {e}")
            print(f"[Fallback] Switching to next fallback model...")
            time.sleep(2)

    return None, None

def analyze_raw_data_with_gemini(api_key, categorized_articles, radar_data, current_date_str):
    prompt = f"""You are a Principal Product Strategist and Tech Briefing Engine.
Analyze the following REAL, VERIFIED live-scraped items from top community & developer sources, deduplicate identical news across sources, and generate a structured business intelligence briefing in Korean.

CRITICAL ZERO-HALLUCINATION RULES:
1. ONLY analyze and summarize the exact real items provided in the input below. NEVER invent products, names, or fake URLs.
2. For "ai_video" (AI Content & Creator Tools), prioritize actual video/audio/image generation tools, LoRA models, avatar creators, and workflow software.
3. Keep the exact "source_url" and "source_name" provided in the input.

INPUT REAL ARTICLES:
{json.dumps(categorized_articles, ensure_ascii=False, indent=2)}

INPUT BENCHMARK & RADAR DATA:
{json.dumps(radar_data, ensure_ascii=False, indent=2)}

OUTPUT STRICT JSON SCHEMA:
{{
  "briefing_items": [
    {{
      "category_id": "ai_models" | "ai_video" | "health_fitness",
      "type_badge": "🚀 New Product" | "💼 B2B / SaaS" | "📱 Consumer App" | "💡 Use-Case & BM",
      "title": "실제 기사 기반의 명확한 국문 헤드라인",
      "target_problem": "타겟 고객 및 해결하려는 구체적 문제",
      "tech_applied": "적용 기술 스택 및 구현 방식",
      "business_insight": "과금 모델 및 사업적 시사점",
      "source_name": "제공된 실제 출처명",
      "source_url": "제공된 실제 URL",
      "tags": ["AI", "SaaS"]
    }}
  ],
  "llm_radar_items": [
    {{
      "badge": "🚀 Model Release" | "📊 Benchmark" | "⚡ API & Infra",
      "title": "실제 출시된 모델명 및 릴리즈 요약",
      "org": "조직명 (OpenAI, Anthropic, Qwen, DeepSeek 등)",
      "summary": "핵심 스펙, 성능 및 벤치마크 변경 사항 요약",
      "source_name": "LLM-Stats / Artificial Analysis",
      "source_url": "https://llm-stats.com/ai-news"
    }}
  ]
}}
"""
    text, used_model = query_gemini_waterfall(api_key, prompt)
    if not text:
        return [], [], None

    try:
        parsed = json.loads(text)
        return parsed.get("briefing_items", []), parsed.get("llm_radar_items", []), used_model
    except Exception as e:
        print(f"[JSON Parse Error] {e}")
        return [], [], used_model

def render_html_dashboard(current_date_str, today_items, past_digests, llm_radar_items=None, used_model=None):
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
                      <span>실제 원문 보기</span>
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
              <p class="text-sm font-semibold text-slate-300">☕ 해당 카테고리에 검증된 신규 상용 솔루션 소식이 없습니다.</p>
              <p class="text-xs text-slate-500 max-w-sm">검증된 소스 풀을 실시간 모니터링 중입니다.</p>
            </div>
            """
            today_cards_html.append(empty_cat_card)

    if total_today_count == 0:
        today_cards_rendered = f"""
        <div class="col-span-full bg-slate-900/50 border border-dashed border-slate-800/80 rounded-2xl p-8 sm:p-10 text-center flex flex-col items-center justify-center gap-3">
          <div class="text-3xl sm:text-4xl">☕</div>
          <h3 class="text-base sm:text-lg font-bold text-slate-200">오늘은 검증된 신규 비즈니스 소식이 없습니다</h3>
          <p class="text-xs sm:text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
            공식 개발자 채널 및 벤치마크 플랫폼에서 실시간 검증된 실제 릴리즈만 수집합니다.
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
                <span class="text-slate-500 font-mono">Verified Source</span>
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
          LLM-Stats 및 Artificial Analysis 실시간 피드를 수집 중입니다.
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

    archive_rendered = "\n".join(archive_days_html) if archive_days_html else """
    <div class="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-6 text-center text-slate-500 text-sm">
      과거 7일간의 누적 헤드라인 아카이브가 이곳에 순차적으로 보관됩니다.
    </div>
    """

    engine_badge = f"Google GenAI ({used_model})" if used_model else "Google GenAI Engine"

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
        글로벌 AI 커뮤니티, 벤치마크 연구소 및 웨어러블 릴리즈를 실시간 통합 분석한 비즈니스 브리핑입니다.
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

    <!-- SECTION 2: LLM STATS & BENCHMARK RADAR -->
    <section class="mb-10 bg-slate-950/70 border border-slate-800/90 rounded-2xl p-4 sm:p-5">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4 pb-3 border-b border-slate-800/80">
        <div>
          <h3 class="text-base font-bold text-slate-100 flex items-center gap-2">
            <span class="text-amber-400">📡</span> Model Radar & Benchmarks
            <span class="text-[11px] font-mono font-normal text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">Live Benchmarks</span>
          </h3>
          <p class="text-xs text-slate-400 mt-0.5">LLM-Stats 및 Artificial Analysis 기반 실시간 릴리즈, 추론 속도 및 가성비 지표입니다.</p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <a href="https://llm-stats.com/ai-news" target="_blank" rel="noopener noreferrer" class="text-[11px] font-mono text-sky-400 hover:underline">LLM-Stats ↗</a>
          <span class="text-slate-700">•</span>
          <a href="https://artificialanalysis.ai/" target="_blank" rel="noopener noreferrer" class="text-[11px] font-mono text-sky-400 hover:underline">Artificial Analysis ↗</a>
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
      <p>Automated by <strong>GitHub Actions</strong> & <strong>{engine_badge}</strong></p>
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
    print("[Pipeline] Starting Verified Full-Source Multi-Channel Harvester...")
    current_date_str = get_current_kst_date()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        print("[CRITICAL ERROR] GEMINI_API_KEY 환경 변수가 비어 있습니다.")
        sys.exit(1)

    history_file = "history.json"
    index_file = "index.html"

    history_data = load_history(history_file)
    pruned_digests = prune_history(history_data, current_date_str, max_days=7)

    # 1. 확정된 소스 풀 전체 수집
    categorized_raw_articles = {}
    for cat in CATEGORIES:
        cat_id = cat["id"]
        raw_items = []
        for src in cat.get("sources", []):
            src_type = src.get("type", "rss")
            src_name = src.get("name", "Source")
            src_url = src.get("url", "")

            if src_type == "rss":
                items = fetch_rss_feed(src_name, src_url, max_items=4)
            else:
                items = fetch_web_snippet(src_name, src_url, max_chars=1200)

            raw_items.extend(items)
            time.sleep(1)  # Rate Limit 방어 딜레이

        # 중복 릴리즈 1차 필터링
        deduped = deduplicate_raw_items(raw_items)
        categorized_raw_articles[cat_id] = deduped
        print(f"[Harvester] Collected {len(deduped)} unique verified items for '{cat_id}'")

    # 2. 벤치마크 및 모델 레이더 수집
    radar_data = fetch_radar_data()
    print(f"[Harvester] Collected {len(radar_data)} radar snippets (LLM-Stats, Artificial Analysis)")

    # 3. Gemini 다단계 우회 분석 실행
    all_today_items, llm_radar_items, used_model = analyze_raw_data_with_gemini(
        api_key, categorized_raw_articles, radar_data, current_date_str
    )

    print(f"\n[Digest] Total verified items: {len(all_today_items)}, Radar items: {len(llm_radar_items)} (Engine: {used_model})")

    # 4. 히스토리 갱신
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

    # 5. HTML 대시보드 렌더링
    html_output = render_html_dashboard(current_date_str, all_today_items, updated_digests, llm_radar_items, used_model)

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"[Success] Successfully generated {index_file} ({len(html_output)} bytes)")

if __name__ == "__main__":
    main()
