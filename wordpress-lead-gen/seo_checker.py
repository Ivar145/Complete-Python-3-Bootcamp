import time

import requests
from bs4 import BeautifulSoup


def check_seo(url: str) -> dict:
    score = 100
    issues = []

    if not url.startswith("http"):
        url = "https://" + url

    if url.startswith("http://"):
        score -= 10
        issues.append("No SSL (site uses HTTP, not HTTPS)")

    try:
        start = time.time()
        response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        elapsed = time.time() - start
    except requests.exceptions.ConnectionError:
        return {"score": 0, "issues": ["Could not connect to website"], "issue_summary": "Connection failed", "blocked": True}
    except requests.exceptions.Timeout:
        return {"score": 0, "issues": ["Website timed out after 15 seconds"], "issue_summary": "Connection timed out", "blocked": True}
    except Exception as e:
        return {"score": 0, "issues": [f"Error loading website: {str(e)}"], "issue_summary": str(e), "blocked": True}

    if response.status_code in (403, 401, 429):
        return {
            "score": 0,
            "issues": [f"Site blocked automated access (HTTP {response.status_code}) — SEO unknown, review manually"],
            "issue_summary": f"Blocked (HTTP {response.status_code})",
            "blocked": True,
        }

    if elapsed > 5:
        score -= 20
        issues.append(f"Very slow load time ({elapsed:.1f}s — should be under 3s)")
    elif elapsed > 3:
        score -= 10
        issues.append(f"Slow load time ({elapsed:.1f}s — should be under 3s)")

    soup = BeautifulSoup(response.text, "html.parser")

    title = soup.find("title")
    if not title or not title.get_text(strip=True):
        score -= 15
        issues.append("Missing title tag")

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content", "").strip():
        score -= 15
        issues.append("Missing meta description")

    h1_tags = soup.find_all("h1")
    if not h1_tags:
        score -= 10
        issues.append("Missing H1 heading tag")

    images = soup.find_all("img")
    missing_alt = [img for img in images if not img.get("alt", "").strip()]
    if missing_alt:
        deduction = min(10, len(missing_alt) * 2)
        score -= deduction
        issues.append(f"{len(missing_alt)} image(s) missing alt text")

    viewport = soup.find("meta", attrs={"name": "viewport"})
    if not viewport:
        score -= 15
        issues.append("Missing viewport meta tag (not mobile-friendly)")

    text_content = soup.get_text(separator=" ", strip=True)
    word_count = len(text_content.split())
    if word_count < 100:
        score -= 10
        issues.append(f"Thin content (only {word_count} words — aim for 300+)")

    try:
        sitemap_url = url.rstrip("/") + "/sitemap.xml"
        sitemap_resp = requests.get(sitemap_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if sitemap_resp.status_code != 200:
            score -= 5
            issues.append("No sitemap.xml found")
    except Exception:
        score -= 5
        issues.append("No sitemap.xml found")

    score = max(0, score)
    issue_summary = issues[0] if issues else "No major issues found"

    return {"score": score, "issues": issues, "issue_summary": issue_summary}
