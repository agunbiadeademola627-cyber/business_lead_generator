import streamlit as st
import pandas as pd
import difflib
import re

# Set up page layout
st.set_page_config(page_title="Fuzzy Lead Generator", page_icon="🎯", layout="wide")

st.title("🎯 Intelligent Lead Generation & Extraction Tool")
st.write("Type a business name below. The system uses fuzzy logic to handle typos and automatically extracts structured contact data.")

# 1. Simulated Raw Directory Data (Simulating chaotic data scraped from public directories)
RAW_DIRECTORY_DATA = [
    {
        "directory_source": "YellowPages Regional",
        "scraped_name": "Alphabet Inc.",
        "owner": "Larry Page / Sergey Brin",
        "raw_text": "Main HQ office. Reach out via email at contact@abc.xyz or dial their main desk lines: +1-650-253-0000 or alt line 555-0199."
    },
    {
        "directory_source": "Chamber of Commerce",
        "scraped_name": "Alcatel-Lucent Enterprise",
        "owner": "Jack Chen",
        "raw_text": "For corporate partnerships contact info@alcatel-lucent.com. Direct phone line is +33-1-40-76-10-10."
    },
    {
        "directory_source": "BizRegistry Open",
        "scraped_name": "Acme Corporation",
        "owner": "Wile E. Coyote",
        "raw_text": "Inquiries regarding anvils can be sent to orders@acme-corp.net. Call us anytime at 1-800-555-ACME."
    }
]

# 2. Text Parsing Helper Functions (Using Regex)
def extract_emails(text):
    # Matches standard email patterns
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    return ", ".join(emails) if emails else "No email found"

def extract_phones(text):
    # Matches various phone formats (e.g., +1-XXX-XXX-XXXX, XXX-XXXX, 1-800-XXX-XXXX)
    phone_pattern = r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\b\d{3}-\d{4}\b'
    phones = re.findall(phone_pattern, text)
    
    # Clean up the output if regex finds multiple matches
    found_phones = [match for match in re.findall(r'\+?\d[\d\-\s]{7,14}\d', text)]
    return ", ".join(found_phones) if found_phones else "No phone line found"

# 3. User Input Interface
search_query = st.text_input("🔍 Enter Business Name (Try typing 'alkabeth' or 'acme'):", placeholder="e.g., alkabeth")

if search_query:
    # Extract all known names from our directory
    known_names = [item["scraped_name"] for item in RAW_DIRECTORY_DATA]
    
    # Find close matches (cutoff=0.4 allows for high error tolerance like alkabeth -> Alphabet)
    matches = difflib.get_close_matches(search_query, known_names, n=1, cutoff=0.4)
    
    if matches:
        matched_name = matches[0]
        st.info(f"💡 Typo detected! Showing closest match for: **{matched_name}**")
        
        # Pull the record associated with the matched name
        record = next(item for item in RAW_DIRECTORY_DATA if item["scraped_name"] == matched_name)
        
        # Run our extraction logic over the messy raw directory text
        extracted_email = extract_emails(record["raw_text"])
        extracted_phone = extract_phones(record["raw_text"])
        
        # Structure the extracted data for display
        lead_data = {
            "Directory Source": [record["directory_source"]],
            "Business Name": [record["scraped_name"]],
            "Business Owner": [record["owner"]],
            "Extracted Email": [extracted_email],
            "Extracted Phone Lines": [extracted_phone]
        }
        
        df_leads = pd.DataFrame(lead_data)
        
        # Display the formatted data
        st.subheader("📊 Structured Lead Result")
        st.dataframe(df_leads, use_container_width=True)
        
        # Download button for the client
        csv = df_leads.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Export Lead to CSV",
            data=csv,
            file_name=f"{matched_name.lower().replace(' ', '_')}_lead.csv",
            mime="text/csv"
        )
        
    else:
        st.error("❌ No business matching that name could be found in the public directories. Try adjusting your search.")