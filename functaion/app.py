from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import re
import os
import time
import sys
import shutil

# Get defaults from environment variables or use hardcoded defaults
DEFAULT_INPUT_DIR = os.path.join(
    os.getenv('WORKSPACE', "."),
    os.getenv('CODEBASE_DIR', ""),
    "logs"
)
DEFAULT_SLEEP_DURATION = int(os.getenv('SLEEP_DURATION', "5"))
DEFAULT_OUTPUT_DIR = os.path.join(
    os.getenv('WORKSPACE', "."),
    os.getenv('CODEBASE_DIR', ""),
    "reports"
)

def get_arguments():
    """Get command line arguments, overriding env vars if provided"""
    input_dir = DEFAULT_INPUT_DIR
    sleep_duration = DEFAULT_SLEEP_DURATION

    if len(sys.argv) > 1:
        input_dir = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            sleep_duration = int(sys.argv[2])
        except ValueError:
            print(f"Warning: Invalid SLEEP_DURATION, using default {DEFAULT_SLEEP_DURATION}")
            sleep_duration = DEFAULT_SLEEP_DURATION

    return input_dir, sleep_duration

def read_file_content(file_path):
    """Read content from a file with error handling"""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Warning: File {file_path} not found")
        return ""
    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
        return ""

def parse_cluster_upgrade(file_content):
    """Parse the EKS cluster upgrade information"""
    result = {}

    cluster_match = re.search(r"EKS Cluster Upgrade Summary - (\w+) \((\w+-\w+-\d+)\)", file_content)
    if cluster_match:
        result['name'] = cluster_match.group(1)
        result['region'] = cluster_match.group(2)
    else:
        result['name'] = "Unknown"
        result['region'] = "Unknown"

    version_match = re.search(r"Current version: ([\d.]+)\n.*upgrade to version ([\d.]+)", file_content)
    if version_match:
        result['current_version'] = version_match.group(1)
        result['target_version'] = version_match.group(2)
    else:
        result['current_version'] = "Unknown"
        result['target_version'] = "Unknown"

    status_match = re.search(r"RESULT: (\w+),([\d.]+),([\d.]+),(\w+)", file_content)
    if status_match:
        result['cluster_name'] = status_match.group(1)
        result['current_version'] = status_match.group(2)
        result['target_version'] = status_match.group(3)
        result['status'] = status_match.group(4)
    else:
        result['cluster_name'] = result.get('name', 'Unknown')
        result['status'] = "Unknown"

    logs = []
    for line in file_content.split('\n'):
        if line.strip() and not line.startswith('RESULT:') and not line.startswith('Cluster Name'):
            logs.append(line.strip())
    result['logs'] = logs

    timestamp_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", file_content)
    if timestamp_match:
        result['timestamp'] = timestamp_match.group(1)
    else:
        result['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return result

def parse_nodegroup_upgrade(file_content):
    """Parse nodegroup upgrade information"""
    nodegroups = []
    logs = []

    result_matches = re.finditer(r"RESULT: ([\w-]+),([\d.]+),([\d.]+),(\w+)", file_content)
    for match in result_matches:
        nodegroups.append({
            'name': match.group(1),
            'current_version': match.group(2),
            'target_version': match.group(3),
            'status': match.group(4),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    if not nodegroups:
        ng_match = re.search(r"Nodegroup '([\w-]+)' version is ([\d.]+). Target is ([\d.]+)", file_content)
        if ng_match:
            nodegroups.append({
                'name': ng_match.group(1),
                'current_version': ng_match.group(2),
                'target_version': ng_match.group(3),
                'status': "Unknown",
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

    for line in file_content.split('\n'):
        if line.strip() and not line.startswith('RESULT:'):
            logs.append(line.strip())

    return nodegroups, logs

def parse_addon_upgrade(file_content):
    """Parse addon upgrade information"""
    addons = []
    errors = []

    addon_matches = re.finditer(r"([\w-]+),([\w.-]+),([\w.-]+),([\w-]+)", file_content)
    for match in addon_matches:
        addons.append({
            'name': match.group(1),
            'current_version': match.group(2),
            'target_version': match.group(3),
            'status': match.group(4)
        })

    error_matches = re.finditer(r"ERROR upgrading addon '([\w-]+)'.*?\n(.*?)(?=\n\S)", file_content, re.DOTALL)
    for match in error_matches:
        errors.append(f"{match.group(1)}: {match.group(2).strip()}")

    if not errors:
        error_matches = re.finditer(r"Error: (.*)", file_content)
        for match in error_matches:
            errors.append(match.group(1))

    return addons, errors

def parse_api_check(file_content):
    """Parse API version check information"""
    result = {
        'logs': [],
        'summary': 'No information found',
        'report_file': 'Not available'
    }

    summary_match = re.search(r"summary=(.*)", file_content)
    if summary_match:
        result['summary'] = summary_match.group(1)
    else:
        summary_match = re.search(r"No deprecated APIs found", file_content)
        if summary_match:
            result['summary'] = "API Check: No deprecated APIs found."

    report_match = re.search(r"Output saved to: ([\w.-]+)", file_content)
    if report_match:
        result['report_file'] = report_match.group(1)

    for line in file_content.split('\n'):
        if line.strip() and not line.startswith('summary=') and not line.startswith('Report:'):
            result['logs'].append(line.strip())

    return result

def main():
    input_dir, sleep_duration = get_arguments()

    if sleep_duration > 0:
        print(f"Sleeping for {sleep_duration} seconds before generating report...")
        time.sleep(sleep_duration)

    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('templates/template.html')

    input_files = {
        'cluster': os.path.join(input_dir, 'eks-cluster-summary.txt'),
        'nodegroup': os.path.join(input_dir, 'eks-node-group.log'),
        'addon': os.path.join(input_dir, 'addon-output.txt'),
        'api_check': os.path.join(input_dir, 'api_version_check_output.log')
    }

    # Read and parse all files
    cluster_upgrade_content = read_file_content(input_files['cluster'])
    nodegroup_content = read_file_content(input_files['nodegroup'])
    addon_content = read_file_content(input_files['addon'])
    api_check_content = read_file_content(input_files['api_check'])

    control_plane = parse_cluster_upgrade(cluster_upgrade_content)
    nodegroups, nodegroup_logs = parse_nodegroup_upgrade(nodegroup_content)
    addons, addon_errors = parse_addon_upgrade(addon_content)
    api_check = parse_api_check(api_check_content)

    cluster_info = {}
    if 'name' in control_plane:
        cluster_info['name'] = control_plane['name']
        if 'region' in control_plane:
            cluster_info['region'] = control_plane['region']

    # Render the template
    html_output = template.render(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        cluster_info=cluster_info,
        control_plane=control_plane,
        nodegroups=nodegroups,
        nodegroup_logs=nodegroup_logs,
        addons=addons,
        addon_errors=addon_errors,
        api_check=api_check
    )

    # Ensure output directory exists
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)

    # Save the report
    report_filename = os.path.join(DEFAULT_OUTPUT_DIR, "eks_upgrade_report.html")
    with open(report_filename, 'w') as f:
        f.write(html_output)

    print(f"Report successfully generated at: {os.path.abspath(report_filename)}")

if __name__ == "__main__":
    main()
