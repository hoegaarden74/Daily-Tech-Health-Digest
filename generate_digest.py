def query_gemini_waterfall(api_key, prompt):
    """503 과부하 시 재시도 로직 및 유효 모델 호출"""
    # 현재 유효한 주력 모델
    target_models = ["gemini-3.6-flash"]
    
    for model_name in target_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }
        data = json.dumps(payload).encode("utf-8")

        # 503 및 일시적 오류 대응: 3회 재시도
        for attempt in range(1, 4):
            print(f"[Pipeline] Requesting analysis via {model_name} (Attempt {attempt}/3)...")
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
                            print(f"[Success] Structured analysis generated via {model_name}")
                            return text, model_name
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8")
                print(f"[API Error] {model_name} HTTP {e.code}: {err_msg[:160]}")
                if e.code in [503, 429] and attempt < 3:
                    wait_time = attempt * 10
                    print(f"[Retry] 서버 지연 감지. {wait_time}초 대기 후 재시도합니다...")
                    time.sleep(wait_time)
                else:
                    break
            except Exception as e:
                print(f"[API Error] {model_name}: {e}")
                if attempt < 3:
                    time.sleep(5)

    return None, None
