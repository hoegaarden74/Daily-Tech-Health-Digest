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
        "feeds": [
            {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
            {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"}
        ]
    },
    {
        "id": "ai_video",
        "name": "AI Content & Creator Tools",
        "icon": "🎬",
        "badge_class": "bg-purple-500/10 text-purple-400 border border-purple-500/30",
        "dot_class": "bg-purple-400",
        "feeds": [
            {"name": "Product Hunt Tech", "url": "https://www.producthunt.com/feed"},
            {"name": "TechCrunch Enterprise", "url": "https://techcrunch.com/category/enterprise/feed/"}
        ]
    },
    {
        "id": "health_fitness",
        "name": "Digital Health & Wellness Tech",
        "icon": "🏃",
        "badge_class": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
        "dot_class": "bg-emerald-400",
        "feeds": [
            {"name": "Gadgets & Wearables", "url": "https://gadgetsandwearables.com/feed/"},
            {"name": "MobiHealthNews", "url": "https://www.mobihealthnews.com/feed"}
        ]
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

def fetch_rss_articles(feed_url, source_name, max_items=4):
    articles = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req = urllib.request.Request(feed_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
            root = ET.fromstring(xml_data)

            for item in root.findall(".//item")[:max_items]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc = item.findtext("description", "").strip()
                clean_desc = re.sub(r"<[^>]+>", " ", desc)[:300].strip()

                if title and link:
                    articles.append({
                        "source_name": source_name,
                        "title": title,
                        "url": link,
                        "summary": clean_desc
                    })
    except Exception as e:
        print(f"[RSS Fetch Error] {source_name} ({feed_url}): {e}")
    return articles

def fetch_llm_stats_raw():
    radar_raw = []
    urls = [
        ("LLM Stats Updates", "https://llm-stats.com/llm-updates"),
        ("LLM Stats AI News", "https://llm-stats.com/ai-news")
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for name, target_url in urls:
        try:
            req = urllib.request.Request(target_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                text_clean = re.sub(r"<script[\s\S]*?</script>", "", html)
                text_clean = re.sub(r"<style[\s\S]*?</style>", "", text_clean)
                text_clean = re.sub(r"<[^>]+>", " ", text_clean)
                text_clean = re.sub(r"\s+", " ", text_clean)[:1200]

                radar_raw.append({
                    "source_name": name,
                    "url": target_url,
                    "content_snippet": text_clean
                })
        except Exception as e:
            print(f"[LLM-Stats Fetch Error] {target_url}: {e}")
            radar_raw.append({
                "source_name": name,
                "url": target_url,
                "content_snippet": "Latest LLM model releases, benchmark leaderboards, and pricing shifts."
            })
    return radar_raw

def query_gemini_single_model(api_key, model_name, prompt):
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
    
    error_reason = None
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            candidates = res_json.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join([p.get("text", "") for p in parts if "text" in p])
                return text, None
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"[REST API Error] {model_name} HTTP {e.code}: {err_msg[:250]}")
        error_reason = f"HTTP {e.code} (일일 쿼터 초과 또는 서버 부하)"
    except Exception as e:
        print(f"[REST API Error] {model_name}: {e}")
        error_reason = "네트워크 타임아웃 또는 서버 응답 지연"
        
    return None, error_reason

def analyze_raw_data_with_gemini(api_key, categorized_articles, llm_stats_data, current_date_str):
    prompt = f"""You are a Principal Product Strategist and Tech Briefing Engine.
Analyze the following REAL, VERIFIED live-scraped articles and generate a structured business intelligence briefing in Korean.

CRITICAL ZERO-HALLUCINATION RULES:
1. ONLY analyze and summarize the exact articles provided below. NEVER invent products, names, or URLs.
2. Keep the exact "source_url" and "source_name" provided in the input.

INPUT REAL ARTICLES:
{json.dumps(categorized_articles, ensure_ascii=False, indent=2)}

INPUT LLM-STATS DATA:
{json.dumps(llm_stats_data, ensure_ascii=False, indent=2)}

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
      "summary": "핵심 스펙, 성능 및 변경 사항 요약",
      "source_name": "LLM Stats",
      "source_url": "https://llm-stats.com/ai-news"
    }}
  ]
}}
"""
    model = "gemini-3.6-flash"
    print(f"[Pipeline] Analyzing verified raw articles with {model}...")
    
    text, error_reason = query_gemini_single_model(api_key, model, prompt)
    if not text:
        return [], [], error_reason

    try:
        parsed = json.loads(text)
        return parsed.get("briefing_items", []), parsed.get("llm_radar_items", []), None
    except Exception as e:
        print(f"[JSON Parse Error] {e}")
        return [], [], "데이터 파싱 에러"

def render_html_dashboard(current_date_str, today_items, past_digests, llm_radar_items=None, api_error=None):
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
              <p class="text-sm font-semibold text-slate-300">☕ 해당 카테고리에 등록된 신규 상용 솔루션 소식이 없습니다.</p>
              <p class="text-xs text-slate-500 max-w-sm">실존하는 피드를 실시간 모니터링 중입니다.</p>
            </div>
            """
            today_cards_html.append(empty_cat_card)

    if total_today_count == 0:
        if api_error:
            today_cards_rendered = f"""
            <div class="col-span-full bg-amber-500/5 border border-amber-500/30 rounded-2xl p-6 sm:p-8 text-center flex flex-col items-center justify-center gap-2.5">
              <div class="text-2xl sm:text-3xl">⚠️</div>
              <h3 class="text-base sm:text-lg font-bold text-amber-300">Gemini API 일일 한도 도달 안내</h3>
              <p class="text-xs sm:text-sm text-slate-300 max-w-lg mx-auto leading-relaxed">
                현재 Gemini API 무료 등급(Free Tier)의 <strong>일일 최대 호출 한도(20 RPD)</strong>에 도달하였거나 서버 일시 과부하({api_error})로 인해 신규 분석이 일시 지연되었습니다.
              </p>
              <div class="mt-2 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono text-slate-400">
                <span>🔄 쿼터 초기화 후 <strong>내일 오전 08:30 정기 스케줄</strong>에 정상 갱신됩니다.</span>
              </div>
            </div>
            """
        else:
            today_cards_rendered = f"""
            <div class="col-span-full bg-slate-900/50 border border-dashed border-slate-800/80 rounded-2xl p-8 sm:p-10 text-center flex flex-col items-center justify-center gap-3">
              <div class="text-3xl sm:text-4xl">☕</div>
              <h3 class="text-base sm:text-lg font-bold text-slate-200">오늘은 검증된 신규 비즈니스 소식이 없습니다</h3>
              <p class="text-xs sm:text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
                인터넷 상의 미확인 추론 데이터를 배제하고, 실시간 검증된 실제 릴리즈만 수집합니다.
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
          llm-stats.com 실시간 업데이트 피드를 수집 중입니다.
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
        실제 언론 및 LLM-Stats에서 실시간 수집된 실제 릴리즈 기사만을 기반으로 분석한 비즈니스 브리핑입니다.
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
      <p>Automated by <strong>GitHub Actions</strong> & <strong>Google GenAI (Gemini 3.6 Flash)</strong></p>
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
          if (!card.textContent.includes('해당 카테고리에 등록된') && !card.textContent.includes('오늘은 검증된') && !card.textContent.includes('한도 도달')) {{
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
    print("[Pipeline] Starting Verified Direct Scraping Briefing Engine (Gemini 3.6 Flash)...")
    current_date_str = get_current_kst_date()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        print("[CRITICAL ERROR] GEMINI_API_KEY 환경 변수가 비어 있습니다.")
        sys.exit(1)

    history_file = "history.json"
    index_file = "index.html"

    history_data = load_history(history_file)
    pruned_digests = prune_history(history_data, current_date_str, max_days=7)

    # 1. 실제 RSS 피드 수집 (100% 실존 기사)
    categorized_raw_articles = {}
    for cat in CATEGORIES:
        cat_id = cat["id"]
        cat_articles = []
        for feed in cat.get("feeds", []):
            items = fetch_rss_articles(feed["url"], feed["name"], max_items=4)
            cat_articles.extend(items)
        categorized_raw_articles[cat_id] = cat_articles
        print(f"[Scraper] Collected {len(cat_articles)} raw verified articles for '{cat_id}'")

    # 2. llm-stats.com 실시간 데이터 수집
    llm_stats_raw = fetch_llm_stats_raw()
    print(f"[Scraper] Collected {len(llm_stats_raw)} feeds from llm-stats.com")

    # 3. Gemini 3.6 Flash 단일 분석 실행
    all_today_items, llm_radar_items, api_error = analyze_raw_data_with_gemini(
        api_key, categorized_raw_articles, llm_stats_raw, current_date_str
    )

    print(f"\n[Digest] Total verified briefings: {len(all_today_items)}, Radar items: {len(llm_radar_items)}")
    if api_error:
        print(f"[Notice] API Limit/Error Status: {api_error}")

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

    html_output = render_html_dashboard(current_date_str, all_today_items, updated_digests, llm_radar_items, api_error)

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"[Success] Successfully generated {index_file} ({len(html_output)} bytes)")

if __name__ == "__main__":
    main()
