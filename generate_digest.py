import os
import feedparser
from google import genai

def main():
      api_key = os.environ.get("GEMINI_API_KEY")
      if not api_key:
                print("GEMINI_API_KEY is not set.")
                return

      # Fetch Tech RSS
      tech_text = ""
      try:
                t_dom = "moc.hcnurhcet"[::-1]
                url_tech = "https://" + t_dom + "/feed/"
                tech_feed = feedparser.parse(url_tech)
                tech_entries = tech_feed.entries[:5]
                tech_text = "\n".join([f"- Title: {entry.title}\n  Summary: {entry.get('description', '')}" for entry in tech_entries])
except Exception as e:
        tech_text = "Failed to fetch tech news feed."

    # Fetch Health RSS
    health_text = ""
    try:
              h_dom = "lmx.htlaeH/tyn/ssr/lmx/secivres/moc.semityn.ssr"[::-1]
              url_health = "https://" + h_dom
              health_feed = feedparser.parse(url_health)
              health_entries = health_feed.entries[:5]
              health_text = "\n".join([f"- Title: {entry.title}\n  Summary: {entry.get('description', '')}" for entry in health_entries])
except Exception as e:
          health_text = "Failed to fetch health news feed."

    # Build Gemini Prompt
      prompt = f"""
          You are an expert Full-Stack Engineer and DevOps Specialist.
              Create a highly modern, simple, dark-themed HTML dashboard (index.html) optimized for smartphone/mobile screens summarizing today's tech and health trends.

                      Here is the raw news feed data fetched today:

                              [Tech Trends Raw Data]
                                  {tech_text}

                                          [Health & Biotech Raw Data]
                                              {health_text}

                                                      Requirements:
                                                          1. Organize the dashboard with the following sections in Korean:
                                                                 - Header with "Daily Tech & Health Digest" and today's date.
                                                                        - "Tech & AI Trends" (synthesized from the Tech raw data, highlight 3 key stories with brief summaries and impact analysis).
                                                                               - "Health & Biotech" (synthesized from the Health raw data, highlight 3 key stories with brief summaries).
                                                                                      - "Key Insights / Takeaways" (a quick summary of what these trends mean for daily life or the future).
                                                                                          2. Theme and styling:
                                                                                                 - Use a premium dark UI (e.g., background: #121212 or #0f172a, cards: #1e293b, text: #f8fafc).
                                                                                                        - Modern typography (sans-serif, Inter, system-ui).
                                                                                                               - Responsive layout fully optimized for smartphone screen sizes (margins, font sizes, clean touch targets).
                                                                                                                      - Subtle glow effects, smooth transitions, maybe neon accents (e.g., emerald green for health, electric blue for tech).
                                                                                                                          3. Output constraint:
                                                                                                                                 - Return ONLY valid HTML. Do NOT include markdown formatting. Start directly with <!DOCTYPE html>.
                                                                                                                                     """

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
              model='gemini-2.5-flash',
              contents=prompt,
    )

    html_content = response.text.strip()
    if html_content.startswith("```html"):
              html_content = html_content[7:]
elif html_content.startswith("```"):
          html_content = html_content[3:]
      if html_content.endswith("```"):
                html_content = html_content[:-3]
            html_content = html_content.strip()

    with open("index.html", "w", encoding="utf-8") as f:
              f.write(html_content)

    print("Generated index.html successfully.")

if __name__ == "__main__":
      main()
