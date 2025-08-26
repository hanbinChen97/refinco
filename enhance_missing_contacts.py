#!/usr/bin/env python3
"""
Enhance companies with missing company_contact_page using Perplexity AI.

This script:
1. Reads Excel file with company data
2. Filters entries where company_contact_page is empty/null  
3. Uses Perplexity AI to find contact info (company_email, company_phone, company_contact_page)
4. Updates the original data with new contact information
5. Outputs statistics and saves enhanced data to new Excel file
"""

import os
import sys
import time
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime

# Add project root to path for imports
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.enhance_info_with_perplexity import _ppx_contact


def enhance_missing_contact_pages(input_file: str, output_file: str) -> None:
    """
    Process Excel file and enhance companies missing contact page info.
    
    Args:
        input_file: Path to input Excel file
        output_file: Path to output Excel file
    """
    print(f"Reading data from: {input_file}")
    df = pd.read_excel(input_file)
    
    # Statistics before processing
    total_companies = len(df)
    missing_contact_page = df['company_contact_page'].isna().sum()
    
    print(f"\n=== INITIAL STATISTICS ===")
    print(f"Total companies: {total_companies}")
    print(f"Missing company_contact_page: {missing_contact_page}")
    print(f"Companies to enhance: {missing_contact_page}")
    
    if missing_contact_page == 0:
        print("No companies need enhancement. Exiting.")
        return
    
    # Filter companies with missing contact page
    companies_to_enhance = df[df['company_contact_page'].isna()].copy()
    
    print(f"\n=== PROCESSING WITH PERPLEXITY AI ===")
    start_time = time.time()
    enhanced_count = 0
    
    # Process each company
    for idx, row in companies_to_enhance.iterrows():
        company_name = row['company_name']
        country = row['country'] if pd.notna(row['country']) else None
        
        print(f"Processing {enhanced_count + 1}/{missing_contact_page}: {company_name}")
        
        try:
            # Get contact info from Perplexity
            contact_info = _ppx_contact(company_name, country)
            
            # Update the original dataframe
            if contact_info.get('company_email'):
                df.at[idx, 'company_email'] = contact_info['company_email']
            if contact_info.get('company_phone'):
                df.at[idx, 'company_phone'] = contact_info['company_phone']
            if contact_info.get('company_contact_page'):
                df.at[idx, 'company_contact_page'] = contact_info['company_contact_page']
                enhanced_count += 1
            
            print(f"  → Enhanced: {bool(contact_info.get('company_contact_page'))}")
            
        except Exception as e:
            print(f"  → Error: {str(e)}")
    
    # Calculate processing time
    processing_time = time.time() - start_time
    
    # Final statistics
    final_missing_contact_page = df['company_contact_page'].isna().sum()
    
    print(f"\n=== FINAL STATISTICS ===")
    print(f"Processing time: {processing_time:.2f} seconds")
    print(f"Companies processed: {missing_contact_page}")
    print(f"Successfully enhanced: {enhanced_count}")
    print(f"Remaining missing contact pages: {final_missing_contact_page}")
    print(f"Enhancement success rate: {enhanced_count/missing_contact_page*100:.1f}%")
    
    # Save enhanced data
    print(f"\nSaving enhanced data to: {output_file}")
    df.to_excel(output_file, index=False)
    print("✅ Enhanced data saved successfully!")
    
    return df


def main():
    """Main function to run the enhancement process."""
    # Default file paths
    input_file = "data/wealth_managers_enhanced.xlsx"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"output/wealth_managers_enhanced_contacts_{timestamp}.xlsx"
    
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found!")
        print("Available files in data/:")
        if os.path.exists("data"):
            for f in os.listdir("data"):
                if f.endswith(".xlsx"):
                    print(f"  - {f}")
        return
    
    # Ensure output directory exists
    os.makedirs("output", exist_ok=True)
    
    # Run enhancement
    enhance_missing_contact_pages(input_file, output_file)


if __name__ == "__main__":
    main()