"""
company_name	country	company_contact_page	company_email	company_phone	ceo	ceo_email	ceo_phone	cofounder	cofounder_email	cofounder_phone
读取 data/wealth_managers_combined_20250818_003634.csv，有这些 column。
比如说数据叫 data。

现在遍历data，如果有 company_contact_page 列，并且 company_email，company_phone有空值：
    - 就 request company_contact_page 。
    - 用 llm 提取 company_email 和 company_phone。
"""

import pandas as pd
import asyncio
from crawl4ai import AsyncWebCrawler
from dotenv import load_dotenv
from utils.openai_llm import generate_text_with_web_search
import logging
from tqdm.asyncio import tqdm

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def scrape_contact_page(url):
    """Scrape the content from a contact page URL using AsyncWebCrawler."""
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            if hasattr(result, 'markdown') and result.markdown:
                return result.markdown[:5000]  # Limit text length
            elif hasattr(result, 'cleaned_html') and result.cleaned_html:
                return result.cleaned_html[:5000]
            return None
    except Exception as e:
        logger.error(f"Error scraping {url}: {str(e)}")
        return None

def extract_contact_info_with_llm(webpage_content):
    """Use OpenAI LLM to extract email and phone from webpage content."""
    prompt = f"""
Please extract the main company contact information from this webpage content:

{webpage_content}

Please return ONLY a JSON object with the following format:
{{
    "company_email": "email@example.com or null if not found",
    "company_phone": "+1234567890 or null if not found"
}}

Rules:
- Look for general company contact email (like info@, contact@, hello@) rather than personal emails
- Look for main company phone number 
- If multiple emails/phones exist, choose the most general/official one
- Return null if no reliable contact information is found
- Do not include any explanation, just return the JSON object
"""
    
    try:
        result = generate_text_with_web_search(prompt)
        response_text = result.get("text", "")
        
        # Try to parse JSON from response
        import json
        # Find JSON in response (sometimes LLM adds extra text)
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        
        if start_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx]
            contact_info = json.loads(json_str)
            
            # Clean up null strings
            email = contact_info.get("company_email")
            phone = contact_info.get("company_phone")
            
            if email == "null" or email == "None":
                email = None
            if phone == "null" or phone == "None":
                phone = None
                
            return email, phone
        else:
            logger.warning("Could not parse JSON from LLM response")
            return None, None
            
    except Exception as e:
        logger.error(f"Error extracting contact info with LLM: {str(e)}")
        return None, None

async def enhance_contact_info():
    """Main function to enhance contact information."""
    # Load the Excel file
    excel_file = "output/wealth_managers_combined_20250818_003634.xlsx"
    
    try:
        df = pd.read_excel(excel_file)
        logger.info(f"Loaded {len(df)} records from {excel_file}")
    except Exception as e:
        logger.error(f"Error loading Excel file: {str(e)}")
        return
    
    # Statistics before processing
    total_records = len(df)
    has_contact_page = df['company_contact_page'].notna().sum()
    missing_email = df['company_email'].isna().sum() | (df['company_email'] == '').sum()
    missing_phone = df['company_phone'].isna().sum() | (df['company_phone'] == '').sum()
    
    # Records that need processing: have contact page AND missing email OR phone
    needs_processing = df[
        (df['company_contact_page'].notna()) & 
        (df['company_contact_page'] != '') &
        (
            (df['company_email'].isna() | (df['company_email'] == '')) |
            (df['company_phone'].isna() | (df['company_phone'] == ''))
        )
    ]
    
    logger.info(f"=== Statistics ===")
    logger.info(f"Total records: {total_records}")
    logger.info(f"Records with contact page: {has_contact_page}")
    logger.info(f"Records missing email: {missing_email}")
    logger.info(f"Records missing phone: {missing_phone}")
    logger.info(f"Records that need processing: {len(needs_processing)}")
    logger.info(f"==================")
    
    enhanced_count = 0
    
    # Use tqdm for progress bar
    for index, row in tqdm(df.iterrows(), total=len(df), desc="Processing records"):
        # Check if we have a contact page URL and missing email/phone
        contact_page = row.get('company_contact_page')
        company_email = row.get('company_email')
        company_phone = row.get('company_phone')
        
        # Skip if no contact page URL
        if pd.isna(contact_page) or not contact_page:
            continue
        
        # Skip if both email and phone are already populated
        if not pd.isna(company_email) and company_email and not pd.isna(company_phone) and company_phone:
            continue
        
        company_name = row.get('company_name', 'Unknown')
        logger.info(f"Processing {company_name} - {contact_page}")
        
        # Scrape the contact page
        webpage_content = await scrape_contact_page(contact_page)
        
        if webpage_content:
            # Extract contact info using LLM
            extracted_email, extracted_phone = extract_contact_info_with_llm(webpage_content)
            
            # Update the dataframe if we found new information
            updated = False
            
            if extracted_email and (pd.isna(company_email) or not company_email):
                df.at[index, 'company_email'] = extracted_email
                logger.info(f"Added email for {company_name}: {extracted_email}")
                updated = True
            
            if extracted_phone and (pd.isna(company_phone) or not company_phone):
                df.at[index, 'company_phone'] = extracted_phone
                logger.info(f"Added phone for {company_name}: {extracted_phone}")
                updated = True
            
            if updated:
                enhanced_count += 1
        
        # Add a small delay to be respectful to websites
        await asyncio.sleep(1)
    
    # Save the enhanced data
    output_csv = "output/wealth_managers_enhanced.csv"
    df.to_csv(output_csv, index=False)
    logger.info(f"Enhanced {enhanced_count} records and saved to {output_csv}")
    
    # Also save as Excel
    output_excel = "output/wealth_managers_enhanced.xlsx"
    df.to_excel(output_excel, index=False)
    logger.info(f"Also saved as Excel: {output_excel}")

if __name__ == "__main__":
    asyncio.run(enhance_contact_info())