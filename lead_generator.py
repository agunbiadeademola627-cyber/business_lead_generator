import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse

# Set up clean, wide dashboard layout
st.set_page_config(page_title="Live Lead Generator", page_icon="🎯", layout="wide")

st.title("🎯 Live Lead Generation & Extraction Tool")
st.write("Type any business name or niche. The system queries live web snippets and extracts verified contact profiles automatically.")

# 1. Text Parsing Helper Functions (Using Regex)
def extract_emails(text):
    # Matches standard email structures
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    # Using set() removes duplicate entries if the same email appears multiple times
    emails = list(set(re.findall(email_pattern, text))) 
    return ", ".join(emails) if emails else "No email found"

def extract_phones(text):
    # Matches standard international and local corporate phone line formats
    phone_pattern = r'\+?\d[\d\-\s\(\)]{8,14}\d'
    raw_phones = re.findall(phone_pattern, text)
    
    # Filter out short random number strings that aren't actually phone lines
    clean_phones = []
    for p in raw_phones:
        digits_only = re.sub(r'\D', '', p)
        if 7 <= len(digits_only) <= 15:
            clean_phones.append(p.strip())
            
    final_phones = list(set(clean_phones)) # Remove duplicates
    return ", ".join(final_phones) if final_phones else "No phone line found"


# 2. User Input Interface
search_query = st.text_input(
    "🔍 Enter Business Name or Niche (e.g., Desjam Limited, Software Company Lagos):", 
    placeholder="e.g., Desjam Limited"
)

if search_query:
    # Give the user visual feedback that the backend scraper is working
    with st.spinner(f"Pinging live servers for '{search_query}'..."):
        
        # Safe URL encoding (converts spaces into %20 or + characters)
        encoded_query = urllib.parse.quote_plus(search_query)
        
        # Build a live public search aggregator target URL
        target_url = f"https://www.google.com/search?q={encoded_query}+contact+email+phone"
        
        # Set desktop headers so servers recognize the script as a legitimate browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            response = requests.get(target_url, headers=headers)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Strip out JavaScript logic or CSS styling before processing raw text strings
                for element in soup(["script", "style"]):
                    element.extract()
                    
                raw_page_text = soup.get_text()
                
                # Execute regex patterns against real text data harvested live
                live_emails = extract_emails(raw_page_text)
                live_phones = extract_phones(raw_page_text)
                
                # 3. Handle and Render Results
                if live_emails != "No email found" or live_phones != "No phone line found":
                    st.success("🎉 Live contact footprints harvested!")
                    
                    # Frame the data for the front-end table layout
                    lead_records = {
                        "Target Search Query": [search_query],
                        "Extracted Emails": [live_emails],
                        "Extracted Phone Lines": [live_phones]
                    }
                    
                    df_leads = pd.DataFrame(lead_records)
                    
                    st.subheader("📊 Structured Lead Result")
                    st.dataframe(df_leads, use_container_width=True)
                    
                    # Convert to exportable CSV format
                    csv_data = df_leads.to_csv(index=False).encode('utf-8')
                    file_safe_name = search_query.lower().replace(" ", "_")
                    
                    st.download_button(
                        label="📥 Export Lead to CSV",
                        data=csv_data,
                        file_name=f"{file_safe_name}_leads.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("⚠️ Connected to live directories, but no public email or phone strings were openly exposed in the search engine snippets. Try adding specific qualifiers like a location or city.")
            
            elif response.status_code == 429:
                st.error("❌ Request blocked by server rate limits. The public directory flags automated loops. To scale this for high-paying clients, we would need to integrate dynamic proxy switching or Playwright.")
            else:
                st.error(f"❌ Connection failed. Mainframe returned error status code: {response.status_code}")
                
        except Exception as err:
            st.error(f"An error occurred while negotiating web traffic: {err}")
