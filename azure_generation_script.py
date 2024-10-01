import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup


def remove_trailing_slash(input_string):
    """Remove trailing slash if present, otherwise leave the string unchanged."""
    return input_string[:-1] if input_string.endswith('/') else input_string

def extract_work_item_id(epic_link):
    """Extract the work item ID from the epic link (supports both query parameter and path)."""
    parsed_url = urlparse(epic_link)
    
    # Check if 'workitem' is a query parameter
    query_params = parse_qs(parsed_url.query)
    if 'workitem' in query_params:
        return query_params['workitem'][0]  # Extract work item from query parameter
    
    # Fallback to extracting from the path (if work item ID is part of the URL path)
    path_parts = parsed_url.path.split('/')
    return path_parts[-1] if path_parts[-1].isdigit() else None

def extract_organization_from_epic_link(epic_link):
    """Extract the organization name from the epic link."""
    try:
        parts = epic_link.split('/')
        return parts[3]  # 'https://dev.azure.com/{organization}/'
    except IndexError:
        return None

def get_projects(organization_url, pat):
    """Fetch all projects from the Azure DevOps organization."""
    url = f"{organization_url}/_apis/projects?api-version=7.0"
    response = requests.get(url, auth=HTTPBasicAuth('', pat))
    
    if response.status_code == 200:
        projects = response.json()['value']
        return [project['name'] for project in projects]
    else:
        print(f"Failed to fetch projects: {response.status_code} - {response.text}")
        return []

def get_json_of_workItem_using_azureDevops_restApis(url, pat, fetched_work_items, work_item_id):
    """Retrieve JSON data for a specific work item, and cache the result to avoid repeated API hits."""
    # Check if the work item has already been fetched
    if work_item_id in fetched_work_items:
        return fetched_work_items[work_item_id]

    response = requests.get(url, auth=HTTPBasicAuth('', pat))
    if response.status_code == 200:
        data = response.json()
        fetched_work_items[work_item_id] = data  # Cache the result
        return data
    return None

def clean_html(raw_html):
    """Remove HTML tags from the raw HTML string."""
    soup = BeautifulSoup(raw_html, "html.parser")
    soup = soup.get_text(separator=" ").strip()
    return soup  # Get text with spaces between elements

def find_key_containing(fields, search_term):
    """Find the first key in fields that contains the search term."""
    for key, value in fields.items():
        if search_term.lower() in key.lower():
            return value
    return None

def collect_work_item_descriptions_and_hierarchy(projects, organization_url, work_item_id, pat, visited_ids=None, work_item_map=None, hierarchy=None, fetched_work_items=None):
    """Recursively collect work item descriptions and build a parent-child hierarchy tree."""
    if visited_ids is None:
        visited_ids = set()  # Initialize the set to keep track of visited work items
    if work_item_map is None:
        work_item_map = {}  # Initialize the map to store work item descriptions
    if fetched_work_items is None:
        fetched_work_items = {}  # Initialize the cache to store fetched work items
    if hierarchy is None:
        hierarchy = {}  # Initialize the hierarchy tree

    # If the work item has already been visited, skip re-fetching it
    if work_item_id in visited_ids:
        return work_item_map, hierarchy

    # Mark the current work item as visited
    visited_ids.add(work_item_id)

    for project in projects:
        url = f"{organization_url}/{project}/_apis/wit/workitems/{work_item_id}?$expand=relations&api-version=7.0"
        data_json = get_json_of_workItem_using_azureDevops_restApis(url, pat, fetched_work_items, work_item_id)
        
        if data_json:
            # Extract and store the description of the current work item
            fields = data_json.get('fields', {})
            type = fields.get('System.WorkItemType', 'No type available')

            if type == 'Bug':
                # Dynamically search for a field containing 'ReproSteps'
                description = "Repro Steps: " + (find_key_containing(fields, 'ReproSteps') or 'No Repro Steps available')
            elif type == 'Test Case':
                # Dynamically search for a field containing 'Steps'
                description = "Steps: " + (find_key_containing(fields, 'Steps') or 'No Steps available')
            else:
                # For other types, get the general description
                description = "Description: " + (fields.get('System.Description', 'No description available'))
                
                # Dynamically search for Acceptance Criteria field
                acceptance_criteria = find_key_containing(fields, 'AcceptanceCriteria')
                if acceptance_criteria:
                    description += '\nAcceptance Criteria: ' + acceptance_criteria

            cleaned_description = clean_html(description).strip()
            work_item_map[work_item_id] = cleaned_description

            # Process related work items via 'relations'
            relations = data_json.get('relations', [])
            related_work_item_ids = []
            parent_work_item = None
            
            for relation in relations:
                if relation.get('rel') == 'System.LinkTypes.Hierarchy-Forward':  # Child of the current work item
                    relation_url = relation.get('url', '')
                    related_work_item_id = relation_url.split('/')[-1]
                    if related_work_item_id.isdigit() and related_work_item_id not in visited_ids:
                        related_work_item_ids.append(related_work_item_id)
                elif relation.get('rel') == 'System.LinkTypes.Hierarchy-Reverse':  # Parent of the current work item
                    parent_work_item = relation.get('url', '').split('/')[-1]

            # Add the current work item to the hierarchy
            if parent_work_item:
                if work_item_id not in hierarchy.get(parent_work_item, []):
                    hierarchy.setdefault(parent_work_item, []).append(work_item_id)
            else:
                if work_item_id not in hierarchy.get(None, []):  # Top-level work item
                    hierarchy.setdefault(None, []).append(work_item_id)

            # Recursively fetch descriptions of related (child) work items
            for related_id in related_work_item_ids:
                collect_work_item_descriptions_and_hierarchy(
                    projects, organization_url, related_id, pat, visited_ids, work_item_map, hierarchy, fetched_work_items
                )

    return work_item_map, hierarchy

def print_hierarchy(hierarchy, work_item_map, work_item_id=None, level=0):
    """Print the hierarchy tree with descriptions."""
    indent = "  " * level
    if work_item_id is None:
        # Print top-level items (those without a parent)
        for top_level_item in hierarchy.get(None, []):
            print(f"{indent}Work Item ID: {top_level_item}\n{work_item_map.get(top_level_item, '')}\n")
            print_hierarchy(hierarchy, work_item_map, top_level_item, level + 1)
    else:
        # Print child items
        for child_item in hierarchy.get(work_item_id, []):
            print(f"{indent}Work Item ID: {child_item}\n{work_item_map.get(child_item, '')}\n")
            print_hierarchy(hierarchy, work_item_map, child_item, level + 1)

def main():
    epic_link = input("Enter the Azure Boards epic link: ").strip()
    pat = input("Enter your Personal Access Token (PAT): ").strip()

    # Remove trailing slash from epic link
    epic_link = remove_trailing_slash(epic_link)
    
    # Extract work item ID from the epic link
    epic_id = extract_work_item_id(epic_link)
    if not epic_id:
        print("Invalid epic link or work item ID not found.")
        return

    # Extract organization name from the epic link
    organization_name = extract_organization_from_epic_link(epic_link)
    if not organization_name:
        print("Could not extract the organization name from the epic link.")
        return

    # Construct the organization URL
    organization_url = f"https://dev.azure.com/{organization_name}"

    # Fetch all projects
    projects = get_projects(organization_url, pat)
    if not projects:
        print("No projects found.")
        return

    # Collect work item descriptions and hierarchy
    work_item_map, hierarchy = collect_work_item_descriptions_and_hierarchy(projects, organization_url, epic_id, pat)

    print(hierarchy)
    for work_item_id, description in work_item_map.items():
        print(f"Work Item ID: {work_item_id}\n{description}\n")
if __name__ == "__main__":
    main()
