import requests
from requests.auth import HTTPBasicAuth
import json
import re

# Cache to store ticket details to avoid hitting the same ticket multiple times
ticket_cache = {}

# Set to track visited tickets and avoid infinite recursion
visited_tickets = set()

# Dictionary to hold the hierarchy flowchart in JSON format
ticket_hierarchy = {}

def extract_ticket_key_from_url(jira_url):
    """
    Extracts the Jira ticket key from a Jira issue URL.
    Args:
        jira_url (str): The Jira issue URL.
    Returns:
        str: The ticket key, or None if the URL format is invalid.
    """
    match = re.search(r'/browse/([A-Z]+-\d+)', jira_url)
    if match:
        return match.group(1)
    else:
        print("Invalid Jira URL format.")
        return None

def get_ticket_data(ticket_key, jira_base_url, email, api_token):
    """
    Fetches Jira ticket data from the Jira API and caches the result.
    Args:
        ticket_key (str): The Jira ticket key (e.g., 'COM-1258').
        jira_base_url (str): The base URL of the Jira instance.
        email (str): The Jira username (email).
        api_token (str): The API token for Jira.
    Returns:
        dict: The JSON data of the Jira ticket, or None if the request fails.
    """
    if ticket_key in ticket_cache:
        return ticket_cache[ticket_key]

    jira_api_url = f"{jira_base_url}/rest/api/2/issue/{ticket_key}"

    response = requests.get(
        jira_api_url,
        auth=HTTPBasicAuth(email, api_token),
        headers={'Content-Type': 'application/json'}
    )

    if response.status_code == 200:
        ticket_data = response.json()
        ticket_cache[ticket_key] = ticket_data
        return ticket_data
    else:
        print(f"Failed to retrieve data for ticket {ticket_key}: {response.status_code}")
        return None

def collect_ticket_information(ticket_key, jira_base_url, email, api_token, parent_ticket=None):
    """
    Recursively collects detailed information for a Jira ticket and its linked issues.
    Args:
        ticket_key (str): The Jira ticket key.
        jira_base_url (str): The base URL of the Jira instance.
        email (str): The Jira username (email).
        api_token (str): The API token for Jira.
        parent_ticket (str, optional): The parent ticket to avoid circular references.
    Returns:
        list: A list containing dictionaries of ticket information.
    """
    if ticket_key in visited_tickets:
        return []

    visited_tickets.add(ticket_key)

    ticket_data = get_ticket_data(ticket_key, jira_base_url, email, api_token)
    if not ticket_data:
        return []

    ticket_info = {'key': ticket_key}

    # Extracting the relevant fields from the ticket
    ticket_info['summary'] = ticket_data['fields'].get('summary', 'No summary available')
    ticket_info['description'] = ticket_data['fields'].get('description', 'No description available')
    ticket_info['status'] = ticket_data['fields'].get('status', {}).get('name', 'No status available')

    # Replace 'customfield_10000' with the actual custom field ID for acceptance criteria if necessary
    ticket_info['acceptance_criteria'] = ticket_data['fields'].get('customfield_10000', 'No acceptance criteria available')

    # Extracting and storing comments if they exist
    comments = ticket_data['fields'].get('comment', {}).get('comments', [])
    ticket_info['comments'] = [comment['body'] for comment in comments] if comments else []

    # Processing linked issues to build the hierarchy
    issue_links = ticket_data['fields'].get('issuelinks', [])
    linked_issues = []

    for link in issue_links:
        if 'inwardIssue' in link:
            linked_issue_key = link['inwardIssue']['key']
            if linked_issue_key != parent_ticket:  # Avoid circular reference to the parent ticket
                linked_issues.append(linked_issue_key)
        elif 'outwardIssue' in link:
            linked_issue_key = link['outwardIssue']['key']
            if linked_issue_key != parent_ticket:
                linked_issues.append(linked_issue_key)

    if linked_issues:
        ticket_hierarchy[ticket_key] = linked_issues

    # Recursively collect information for linked tickets
    linked_tickets_info = []
    for linked_issue_key in linked_issues:
        linked_tickets_info.extend(collect_ticket_information(linked_issue_key, jira_base_url, email, api_token, parent_ticket=ticket_key))

    return [ticket_info] + linked_tickets_info

def display_ticket_hierarchy(ticket_hierarchy):
    """
    Displays the ticket hierarchy in JSON format.
    Args:
        ticket_hierarchy (dict): The ticket hierarchy to display.
    """
    print("Hierarchy Flowchart (JSON format):")
    print(json.dumps(ticket_hierarchy, indent=4))

def display_ticket_details(ticket_details):
    """
    Displays details of the Jira tickets in a human-readable format.
    Args:
        ticket_details (list): List of dictionaries containing ticket information.
    """
    for ticket in ticket_details:
        print(f"Issue Key: {ticket['key']}")
        print(f"Summary: {ticket['summary']}")
        print(f"Description: {ticket['description']}")
        print(f"Status: {ticket['status']}")
        print(f"Acceptance Criteria: {ticket['acceptance_criteria']}")
        if ticket['comments']:
            print("Comments:")
            for comment in ticket['comments']:
                print(f"- {comment}")
        print("\n")

def main():
    """
    Main function to collect and display Jira ticket data and its linked issues.
    """
    jira_url = input("Enter Jira epic URL: ")  # Example: https://gemecosystem.atlassian.net/browse/COM-1258
    email = input("Enter Jira email (username): ")  # Example: kiran.kumari@geminisolutions.com
    api_token = input("Enter Jira API token: ")

    # Extracting ticket key from the URL
    ticket_key = extract_ticket_key_from_url(jira_url)
    if not ticket_key:
        return

    # Extracting Jira base URL from the provided Jira link
    jira_base_url = re.match(r"(https://[^/]+)", jira_url).group(1)

    # Collecting ticket information recursively for the ticket and its linked issues
    ticket_details = collect_ticket_information(ticket_key, jira_base_url, email, api_token)

    # Displaying all collected ticket details
    display_ticket_details(ticket_details)

    # Displaying the ticket hierarchy flowchart in JSON format
    display_ticket_hierarchy(ticket_hierarchy)

if __name__ == "__main__":
    main()
