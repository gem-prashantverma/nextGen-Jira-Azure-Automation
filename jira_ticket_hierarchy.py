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

def validate_jira_credentials(jira_base_url, email, api_token):
    jira_api_url = f"{jira_base_url}/rest/api/2/myself"
    response = requests.get(
        jira_api_url,
        auth=HTTPBasicAuth(email, api_token),
        headers={'Content-Type': 'application/json'}
    )

    try:
        response_data = response.json()

        if response.status_code == 200:
            return True
        else:
            print(f"Invalid Jira credentials: {response.status_code} - {response_data.get('errorMessages', 'Unknown error')}")
            return False
    except requests.exceptions.JSONDecodeError:
        print(f"Invalid response from Jira when validating credentials. Status Code: {response.status_code}, Response Text: {response.text}")
        return False


def check_html_content(data):
    stripped_data = data.strip()
    if data.strip().startswith('<!DOCTYPE html>') or re.search(r'<[^>]+>', stripped_data):
        return 'The site may be unavailable or the URL is incorrect.'
    else:
        return str(data)


def validate_jira_ticket_access(ticket_key, jira_base_url, email, api_token):
    jira_api_url = f"{jira_base_url}/rest/api/2/issue/{ticket_key}"
    response = requests.get(
        jira_api_url,
        auth=HTTPBasicAuth(email, api_token),
        headers={'Content-Type': 'application/json'}
    )

    try:
        response_data = response.json()

        if response.status_code == 200:
            if jira_base_url not in response_data.get('self', ''):
                print(f"The ticket {ticket_key} does not belong to the Jira base URL: {jira_base_url}")
                return False
            return True
        else:
            print(f"Access denied to ticket {ticket_key}: {response.status_code} - {response_data.get('errorMessages', 'Unknown error')}")
            return False
    except requests.exceptions.JSONDecodeError:
        print(f"Invalid response from Jira when validating ticket access. Status Code: {response.status_code}, Response Text: {response.text}")
        return False


def extract_ticket_key_from_url(jira_url):
    match = re.search(r'/browse/([A-Z]+-\d+)', jira_url)
    if match:
        return match.group(1)
    else:
        print("Invalid Jira URL format.")
        return None


def get_ticket_data(ticket_key, jira_base_url, email, api_token):
    if ticket_key in ticket_cache:
        return ticket_cache[ticket_key]

    jira_api_url = f"{jira_base_url}/rest/api/2/issue/{ticket_key}"

    response = requests.get(
        jira_api_url,
        auth=HTTPBasicAuth(email, api_token),
        headers={'Content-Type': 'application/json'}
    )

    try:
        ticket_data = response.json()
        ticket_cache[ticket_key] = ticket_data
        return ticket_data
    except requests.exceptions.JSONDecodeError:
        print(f"Failed to retrieve data for ticket {ticket_key}: Status Code {response.status_code}, Response Text: {response.text}")
        return None


# New function to fetch child issues using the provided endpoint
def get_child_issues(parent_key, jira_base_url, email, api_token):
    search_url = f'{jira_base_url}/rest/api/3/search?jql="Parent Link"={parent_key}'

    response = requests.get(
        search_url,
        auth=HTTPBasicAuth(email, api_token),
        headers={'Content-Type': 'application/json'}
    )

    try:
        search_results = response.json()
        if response.status_code == 200:
            # Extract child issue keys from search results
            child_issues = [issue['key'] for issue in search_results.get('issues', [])]
            return child_issues
        else:
            print(f"Failed to fetch child issues for {parent_key}: {response.status_code} - {search_results.get('errorMessages', 'Unknown error')}")
            return []
    except requests.exceptions.JSONDecodeError:
        print(f"Failed to parse response for child issues: Status Code {response.status_code}, Response Text: {response.text}")
        return []


def collect_ticket_information(ticket_key, jira_base_url, email, api_token, parent_ticket=None):
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

    # Fetching child issues using the new endpoint
    child_issues = get_child_issues(ticket_key, jira_base_url, email, api_token)

    # Adding linked and child tickets to the hierarchy
    if linked_issues or child_issues:
        ticket_hierarchy[ticket_key] = linked_issues + child_issues

    # Recursively collect information for linked and child tickets
    linked_and_child_tickets_info = []
    for linked_issue_key in linked_issues + child_issues:
        linked_and_child_tickets_info.extend(
            collect_ticket_information(linked_issue_key, jira_base_url, email, api_token, parent_ticket=ticket_key)
        )

    return [ticket_info] + linked_and_child_tickets_info


def display_ticket_hierarchy(ticket_hierarchy):
    print("Hierarchy Flowchart (JSON format):")
    print(json.dumps(ticket_hierarchy, indent=4))


def display_ticket_details(ticket_details):
    output = ""
    for ticket in ticket_details:
        output += f"Issue Key: {ticket['key']}\n"
        output += f"Summary: {ticket['summary']}\n"
        output += f"Description: {ticket['description']}\n"
        output += f"Status: {ticket['status']}\n"
        output += f"Acceptance Criteria: {ticket['acceptance_criteria']}\n"
        if ticket['comments']:
            output += "Comments:\n"
            for comment in ticket['comments']:
                output += f"- {comment}\n"
        output += "\n"
    return output


def main():
    jira_url = input("Enter Jira epic URL: ")  # Example: https://gemecosystem.atlassian.net/browse/COM-1258
    email = input("Enter Jira email (username): ")  # Example: kiran.kumari@geminisolutions.com
    api_token = input("Enter Jira API token: ")

    # Extracting ticket key from the URL
    ticket_key = extract_ticket_key_from_url(jira_url)
    if not ticket_key:
        return

    jira_base_url = 'https://gemecosystem.atlassian.net'

    # Step 1: Validate Jira credentials
    if not validate_jira_credentials(jira_base_url, email, api_token):
        return

    # Step 2: Validate access to the given Jira ticket (epic link)
    if not validate_jira_ticket_access(ticket_key, jira_base_url, email, api_token):
        return

    # Step 3: Collecting ticket information recursively for the ticket, its linked issues, and its child tickets
    ticket_details = collect_ticket_information(ticket_key, jira_base_url, email, api_token)

    # Displaying all collected ticket details as a single string
    all_ticket_details = display_ticket_details(ticket_details)
    print(all_ticket_details)

    # Displaying the ticket hierarchy flowchart in JSON format (if needed)
    display_ticket_hierarchy(ticket_hierarchy)


if __name__ == "__main__":
    main()
