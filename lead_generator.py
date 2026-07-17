import streamlit as st
import pandas as pd
import requests
import re
import time
from bs4 import BeautifulSoup

st.set_page_config(page_title="Live Lead Generator", page_icon="🎯", layout="wide")

st.title("🎯 Live Lead Generation Tool")
st.write(
    "Search real businesses from **OpenStreetMap** — a free, open, international "
    "business directory. Enter a niche (e.g. *logistics companies*) plus a city/country, "
    "or a specific business name."
)

# OpenStreetMap requires a descriptive User-Agent as part of its usage policy.
HEADERS = {"User-Agent": "LeadGenDashboard/1.0 (personal lead-gen tool)"}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_PATTERN = r'\+?\d[\d\-\s\(\)]{8,14}\d'


# ---------- Step 1: turn a location string into a bounding box ----------

def geocode_location(location_text):
    """Return (south, west, north, east) bounding box for a place name, or None."""
    params = {
        "q": location_text,
        "format": "jsonv2",
        "limit": 1,
    }
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json()
    except Exception:
        return None

    if not results:
        return None

    bbox = results[0].get("boundingbox")  # [south, north, west, east] as strings
    if not bbox:
        return None
    south, north, west, east = map(float, bbox)
    return south, west, north, east


# ---------- Step 2: query Overpass for businesses matching a keyword in that area ----------

def overpass_search(keyword, bbox, max_results=15):
    south, west, north, east = bbox
    bbox_str = f"{south},{west},{north},{east}"

    query = f"""
    [out:json][timeout:25];
    (
      node["name"~"{keyword}",i]({bbox_str});
      way["name"~"{keyword}",i]({bbox_str});
    );
    out center {max_results * 3};
    """

    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    return data.get("elements", [])


# ---------- Step 3: direct name lookup (for a specific business, no location needed) ----------

def nominatim_direct_search(name, max_results=10):
    params = {
        "q": name,
        "format": "jsonv2",
        "extratags": 1,
        "addressdetails": 1,
        "limit": max_results,
    }
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


# ---------- Step 4: enrich missing contact info from the business's own website ----------

def extract_emails(text):
    emails = set(re.findall(EMAIL_PATTERN, text))
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
    import urllib.parse
    parsed = urllib.parse.urlparse(base_url)
    if not parsed.scheme:
        base_url = "https://" + base_url
        parsed = urllib.parse.urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    for path in ("/contact", "/contact-us", "/about", "/about-us"):
        candidate_url = root + path
        try:
            resp = requests.head(candidate_url, headers=HEADERS, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                return candidate_url
        except Exception:
            continue
    return None


def enrich_from_website(row):
    """If phone/email are missing but a website is known, check that site directly."""
    website = row.get("Website")
    if not website or website == "Not listed":
        return row
    if row["Phone"] != "Not listed" and row["Email"] != "Not listed":
        return row  # already complete, skip the extra request

    url = website if website.startswith("http") else "https://" + website
    combined_text = fetch_page_text(url)

    contact_url = find_contact_page(url)
    if contact_url:
        combined_text += " " + fetch_page_text(contact_url)

    if row["Email"] == "Not listed":
        found_emails = extract_emails(combined_text)
        if found_emails:
            row["Email"] = ", ".join(found_emails)

    if row["Phone"] == "Not listed":
        found_phones = extract_phones(combined_text)
        if found_phones:
            row["Phone"] = ", ".join(found_phones)

    return row


# ---------- Helpers to turn raw OSM tags into a clean row ----------

def build_address(tags):
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:city"),
        tags.get("addr:state"),
        tags.get("addr:country"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else "Not listed"


def row_from_overpass_element(el):
    tags = el.get("tags", {})
    name = tags.get("name", "Unnamed")
    phone = tags.get("phone") or tags.get("contact:phone") or "Not listed"
    email = tags.get("email") or tags.get("contact:email") or "Not listed"
    website = tags.get("website") or tags.get("contact:website") or "Not listed"
    address = build_address(tags)
    return {
        "Business": name,
        "Address": address,
        "Phone": phone,
        "Email": email,
        "Website": website,
    }


def row_from_nominatim_result(res):
    extratags = res.get("extratags") or {}
    name = res.get("name") or res.get("display_name", "").split(",")[0]
    phone = extratags.get("phone") or extratags.get("contact:phone") or "Not listed"
    email = extratags.get("email") or extratags.get("contact:email") or "Not listed"
    website = extratags.get("website") or extratags.get("contact:website") or "Not listed"
    address = res.get("display_name", "Not listed")
    return {
        "Business": name,
        "Address": address,
        "Phone": phone,
        "Email": email,
        "Website": website,
    }


# ---------- UI ----------

col1, col2 = st.columns([2, 1])
with col1:
    query = st.text_input(
        "🔍 Niche or Business Name",
        placeholder="e.g., logistics companies  OR  Google",
    )
with col2:
    location = st.text_input(
        "📍 City / Country (optional but recommended for niches)",
        placeholder="e.g., Lagos, Nigeria",
    )

max_results = st.slider("Max leads to fetch", min_value=1, max_value=25, value=10)
run_search = st.button("Generate Leads", type="primary")

if run_search:
    if not query:
        st.warning("Please enter a business name or niche first.")
    else:
        leads = []

        with st.status("Working on it...", expanded=True) as status:
            if location:
                status.write(f"Step 1/3: Locating '{location}' on the map...")
                bbox = geocode_location(location)

                if not bbox:
                    status.update(label="Couldn't find that location", state="error")
                    st.error(
                        "❌ Couldn't resolve that location. Try a more common spelling "
                        "(e.g. 'Lagos, Nigeria' instead of just 'Lagos') or remove it."
                    )
                    st.stop()

                status.write(f"Step 2/3: Searching for '{query}' businesses in the area...")
                elements = overpass_search(query, bbox, max_results=max_results)

                status.write(f"Step 3/3: Formatting {len(elements)} raw result(s)...")
                seen_names = set()
                for el in elements:
                    row = row_from_overpass_element(el)
                    if row["Business"] in seen_names:
                        continue
                    seen_names.add(row["Business"])
                    leads.append(row)
                    if len(leads) >= max_results:
                        break

            else:
                status.write("Step 1/2: Looking up matches for that name worldwide...")
                results = nominatim_direct_search(query, max_results=max_results)

                status.write(f"Step 2/2: Formatting {len(results)} raw result(s)...")
                for res in results:
                    leads.append(row_from_nominatim_result(res))

            # Enrichment pass: only for leads missing phone/email AND having a known website.
            to_enrich = [
                l for l in leads
                if l.get("Website", "Not listed") != "Not listed"
                and (l["Phone"] == "Not listed" or l["Email"] == "Not listed")
            ]

            if to_enrich:
                status.write(
                    f"Step extra: {len(to_enrich)} lead(s) missing contact info — "
                    "checking their own websites directly..."
                )
                enrich_progress = st.progress(0)
                for i, row in enumerate(to_enrich):
                    enrich_from_website(row)
                    enrich_progress.progress((i + 1) / len(to_enrich))
                    time.sleep(0.5)  # be polite to each business's server

            status.update(label="Done!", state="complete")

        if not leads:
            st.warning(
                "⚠️ No matching businesses found. Tips:\n"
                "- Add a location (helps a lot for niche searches like 'logistics companies')\n"
                "- Try a shorter/simpler keyword (e.g. 'logistics' instead of 'logistics companies')\n"
                "- Double-check the spelling of the location"
            )
        else:
            df_leads = pd.DataFrame(leads)
            has_contact = ((df_leads["Phone"] != "Not listed") | (df_leads["Email"] != "Not listed")).any()

            if has_contact:
                st.success(f"🎉 Found {len(leads)} lead(s), some with contact details.")
            else:
                st.info(
                    f"Found {len(leads)} business(es), but none have a phone/email tagged "
                    "in OpenStreetMap. You'll still have names, addresses, and websites to work from."
                )

            st.subheader("📊 Structured Lead Results")
            st.dataframe(df_leads, use_container_width=True)

            csv_data = df_leads.to_csv(index=False).encode("utf-8")
            file_safe_name = query.lower().replace(" ", "_")
            st.download_button(
                label="📥 Export Leads to CSV",
                data=csv_data,
                file_name=f"{file_safe_name}_leads.csv",
                mime="text/csv",
            )

            st.caption(
                "Data sourced from OpenStreetMap (openstreetmap.org contributors). Where OSM had no "
                "phone/email on file, this tool additionally checked that business's own listed website "
                "for publicly posted contact details. Always follow applicable email/marketing laws "
                "(CAN-SPAM, NDPR, GDPR, etc.) before outreach."
            )
