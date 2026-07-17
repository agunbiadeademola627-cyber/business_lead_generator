import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import urllib.parse

st.set_page_config(page_title="Live Lead Generator", page_icon="🎯", layout="wide")

st.title("🎯 Live Lead Generation & Extraction Tool")
st.write(
    "Type a business name or a niche (e.g. 'logistics companies'). "
    "The tool finds real business websites and pulls the contact details "
    "(email / phone) those businesses have publicly listed on their own site."
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_PATTERN = r'\+?\d[\d\-\s\(\)]{8,14}\d'

# Domains that are never real "leads" - search engines, social platforms, directories etc.
SKIP_DOMAINS = (
    "google.", "youtube.", "facebook.", "instagram.", "linkedin.", "twitter.", "x.com",
    "yelp.", "wikipedia.", "pinterest.", "tiktok.", "reddit.", "duckduckgo.", "bing.",
    "yellowpages.", "maps.google", "amazon.", "indeed.", "glassdoor.",
)


# ---------- Extraction helpers ----------

def extract_emails(text):
    emails = set(re.findall(EMAIL_PATTERN, text))
    # Filter out obvious junk matches (image filenames etc. that slip past the pattern)
    emails = {e for e in emails if not re.search(r'\.(png|jpg|jpeg|gif|svg|webp)$', e, re.I)}
    return sorted(emails)


def extract_phones(text):
    raw_phones = re.findall(PHONE_PATTERN, text)
    clean = set()
    for p in raw_phones:
        digits_only = re.sub(r'\D', '', p)
        if 7 <= len(digits_only) <= 15:
            clean.add(p.strip())
    return sorted(clean)


# ---------- Search ----------

def search_duckduckgo(query, max_results=8):
    """Return a list of (title, url) results from DuckDuckGo's HTML endpoint."""
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    try:
        resp = requests.post(url, headers=HEADERS, timeout=10)
    except Exception:
        return []

    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for a in soup.select("a.result__a"):
        href = a.get("href")
        title = a.get_text(strip=True)
        if not href:
            continue
        domain = urllib.parse.urlparse(href).netloc.lower()
        if any(skip in domain for skip in SKIP_DOMAINS):
            continue
        if href.startswith("http"):
            results.append((title, href))
        if len(results) >= max_results:
            break
    return results


# ---------- Site scraping ----------

def fetch_page_text(url, timeout=8):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.extract()
        return soup.get_text(separator=" ")
    except Exception:
        return ""


def find_contact_page(base_url):
    """Try common contact/about page paths on the same domain."""
    parsed = urllib.parse.urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    candidates = ["/contact", "/contact-us", "/about", "/about-us"]
    for path in candidates:
        candidate_url = root + path
        try:
            resp = requests.head(candidate_url, headers=HEADERS, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                return candidate_url
        except Exception:
            continue
    return None


def scrape_business(name, url):
    """Scrape a business's homepage (and contact page if found) for email/phone."""
    combined_text = fetch_page_text(url)

    contact_url = find_contact_page(url)
    if contact_url:
        combined_text += " " + fetch_page_text(contact_url)

    emails = extract_emails(combined_text)
    phones = extract_phones(combined_text)

    return {
        "Business": name,
        "Website": url,
        "Emails": ", ".join(emails) if emails else "Not listed",
        "Phones": ", ".join(phones) if phones else "Not listed",
    }


# ---------- UI ----------

search_query = st.text_input(
    "🔍 Enter Business Name or Niche",
    placeholder="e.g., Google  OR  logistics companies in Lagos",
)

max_results = st.slider("Max businesses to check", min_value=1, max_value=15, value=6)

if search_query:
    with st.spinner(f"Searching for businesses matching '{search_query}'..."):
        found = search_duckduckgo(search_query, max_results=max_results)

    if not found:
        st.error(
            "❌ No results came back from the search step. This can happen if the "
            "search provider is rate-limiting this session — wait a moment and try again, "
            "or narrow the query (add a city/region)."
        )
    else:
        st.info(f"Found {len(found)} candidate site(s). Visiting each for contact info...")
        progress = st.progress(0)
        leads = []

        for i, (title, url) in enumerate(found):
            leads.append(scrape_business(title or url, url))
            progress.progress((i + 1) / len(found))
            time.sleep(0.5)  # be polite, avoid hammering sites back-to-back

        df_leads = pd.DataFrame(leads)
        has_any_contact = (
            (df_leads["Emails"] != "Not listed") | (df_leads["Phones"] != "Not listed")
        ).any()

        if has_any_contact:
            st.success("🎉 Leads gathered from publicly listed business contact info.")
        else:
            st.warning(
                "⚠️ Found businesses, but none publicly list an email or phone on their "
                "homepage/contact page. Try a more specific niche or a different region."
            )

        st.subheader("📊 Structured Lead Results")
        st.dataframe(df_leads, use_container_width=True)

        csv_data = df_leads.to_csv(index=False).encode("utf-8")
        file_safe_name = search_query.lower().replace(" ", "_")
        st.download_button(
            label="📥 Export Leads to CSV",
            data=csv_data,
            file_name=f"{file_safe_name}_leads.csv",
            mime="text/csv",
        )

        st.caption(
            "Note: this only surfaces contact details a business has already made public "
            "on its own website. Always follow applicable email/marketing laws "
            "(e.g. CAN-SPAM, NDPR, GDPR) before using these for outreach."
        )
