#!/usr/bin/env python3
"""
Mock service for email subject analysis.
"""

import json
import random
from typing import List, Dict, Any

# Business categories
BUSINESS_CATEGORIES = [
    "timesheet",
    "approval",
    "staffing",
    "sow",
    "finance-review",
    "general"
]

# Sample clusters for each category
CATEGORY_CLUSTERS = {
    "timesheet": ["January 2024", "February 2024", "March 2024", "Q1 2024", "Weekly", "Monthly"],
    "approval": ["Project Alpha", "Project Beta", "Budget", "Design", "Proposal", "Contract"],
    "staffing": ["New Hire", "Client Onboarding", "Resource Allocation", "Team Assignment"],
    "sow": ["Project Alpha", "Project Beta", "Client X", "Client Y", "Revision", "Draft"],
    "finance-review": ["Q1 2024", "Q2 2024", "Budget", "Forecast", "Expenses", "Revenue"],
    "general": ["Team Update", "Announcement", "Meeting", "Follow-up", "Reminder", "Status"]
}

# Keywords for each category
CATEGORY_KEYWORDS = {
    "timesheet": ["timesheet", "time sheet", "time tracking", "hours", "time report"],
    "approval": ["approve", "approval", "review", "sign off", "authorize", "permission"],
    "staffing": ["staffing", "resource", "allocation", "assign", "team", "hire", "recruitment"],
    "sow": ["sow", "statement of work", "scope", "proposal", "contract"],
    "finance-review": ["finance", "financial", "budget", "expense", "cost", "revenue", "forecast"],
    "general": []  # Default category
}

def categorize_subject(subject: str) -> Dict[str, Any]:
    """
    Categorize a subject line.
    
    Args:
        subject: Email subject line
        
    Returns:
        Dictionary with tag, cluster, and subject
    """
    # Convert subject to lowercase for case-insensitive matching
    subject_lower = subject.lower()
    
    # Find matching category based on keywords
    tag = "general"  # Default category
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in subject_lower for keyword in keywords):
            tag = category
            break
    
    # Select a cluster based on the category
    clusters = CATEGORY_CLUSTERS.get(tag, CATEGORY_CLUSTERS["general"])
    
    # Try to extract a meaningful cluster from the subject
    # For example, if it contains a month name or project name
    cluster = random.choice(clusters)
    
    # For timesheet category, try to extract month/period
    if tag == "timesheet":
        months = ["january", "february", "march", "april", "may", "june", 
                 "july", "august", "september", "october", "november", "december"]
        for month in months:
            if month in subject_lower:
                cluster = month.capitalize()
                # Check if there's a year after the month
                month_pos = subject_lower.find(month)
                after_month = subject_lower[month_pos + len(month):].strip()
                if after_month and after_month[0].isdigit():
                    # Extract up to 4 digits for the year
                    year = ""
                    for char in after_month:
                        if char.isdigit() and len(year) < 4:
                            year += char
                        elif year:
                            break
                    if year:
                        cluster = f"{cluster} {year}"
                break
    
    # For project-related categories, try to extract project name
    if tag in ["approval", "sow"]:
        project_indicators = ["project", "proj", "client"]
        for indicator in project_indicators:
            if indicator in subject_lower:
                indicator_pos = subject_lower.find(indicator)
                after_indicator = subject_lower[indicator_pos + len(indicator):].strip()
                if after_indicator:
                    # Extract the next word as the project name
                    words = after_indicator.split()
                    if words:
                        project_name = words[0].capitalize()
                        if len(words) > 1 and words[1][0].isupper():
                            project_name += " " + words[1]
                        cluster = project_name
                        break
    
    return {
        "tag": tag,
        "cluster": cluster,
        "subject": subject
    }

def analyze_subjects(subjects: List[str]) -> List[Dict[str, Any]]:
    """
    Analyze a list of email subject lines.
    
    Args:
        subjects: List of email subject lines
        
    Returns:
        List of analysis results
    """
    return [categorize_subject(subject) for subject in subjects]

# Example usage
if __name__ == "__main__":
    test_subjects = [
        "Timesheet approval for March 2024",
        "Please review SOW for Project Alpha",
        "Staffing request for new client onboarding",
        "Finance review meeting - Q1 2024",
        "Weekly team update"
    ]
    
    results = analyze_subjects(test_subjects)
    print(json.dumps(results, indent=2))
