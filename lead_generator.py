import streamlit as st
import pandas as pd
import requests
import time

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
                "Data sourced from OpenStreetMap (openstreetmap.org contributors), an open "
                "map/business database. Contact info reflects only what's been publicly tagged there. "
                "Always follow applicable email/marketing laws (CAN-SPAM, NDPR, GDPR, etc.) before outreach."
            )
