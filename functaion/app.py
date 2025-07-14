from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import re
import os
import time
import sys

# Configuration
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
    """Parse command line arguments"""
    input_dir = DEFAULT_INPUT_DIR
    sleep_duration = DEFAULT_SLEEP_DURATION
    
    if len(sys.argv) > 1:
        input_dir = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            sleep_duration = int(sys.argv[2])
        except ValueError:
            print(f"Warning: Invalid sleep duration, using default {DEFAULT_SLEEP_DURATION}")
    
    return input_dir, sleep_duration

def read_file_content(file_path):
    """Read file content with error handling"""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error reading {file_path}: {str(e)}")
        return None

def parse_cluster_upgrade(content):
    """Parse cluster upgrade information"""
    if not content:
        return None
        
    result = {
        'name': "Unknown",
        'region': "Unknown",
        'current_version': "Unknown",
        'target_version': "Unknown",
        'status': "Unknown",
        'logs': []
    }

    # Extract cluster info
    cluster_match = re.search(r"EKS Cluster Upgrade Summary - (\w+) \((\w+-\w+-\d+)\)", content)
    if cluster_match:
        result['name'] = cluster_match.group(1)
        result['region'] = cluster_match.group(2)

    # Extract versions
    version_match = re.search(r"Current version: ([\d.]+).*?upgrade to version ([\d.]+)", content, re.DOTALL)
    if version_match:
        result['current_version'] = version_match.group(1)
        result['target_version'] = version_match.group(2)

    # Extract status
    status_match = re.search(r"RESULT: (\w+),([\d.]+),([\d.]+),(\w+)", content)
    if status_match:
        result.update({
            'cluster_name': status_match.group(1),
            'current_version': status_match.group(2),
            'target_version': status_match.group(3),
            'status': status_match.group(4)
        })

    # Extract logs
    result['logs'] = [line.strip() for line in content.split('\n') 
                     if line.strip() and not line.startswith('RESULT:')]

    # Extract timestamp
    timestamp_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", content)
    result['timestamp'] = timestamp_match.group(1) if timestamp_match else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return result

def parse_nodegroup_upgrade(content):
    """Parse nodegroup upgrade information"""
    if not content:
        return [], []
        
    nodegroups = []
    logs = []

    # Extract nodegroup results
    for match in re.finditer(r"RESULT: ([\w-]+),([\d.]+),([\d.]+),(\w+)", content):
        nodegroups.append({
            'name': match.group(1),
            'current_version': match.group(2),
            'target_version': match.group(3),
            'status': match.group(4),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    # Fallback for different format
    if not nodegroups:
        match = re.search(r"Nodegroup '([\w-]+)' version is ([\d.]+). Target is ([\d.]+)", content)
        if match:
            nodegroups.append({
                'name': match.group(1),
                'current_version': match.group(2),
                'target_version': match.group(3),
                'status': "Unknown",
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

    # Extract logs
    logs = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('RESULT:')]

    return nodegroups, logs

def parse_addon_upgrade(content):
    """Parse addon upgrade information"""
    if not content:
        return [], []
        
    addons = []
    errors = []

    # Extract addon info
    for match in re.finditer(r"([\w-]+),([\w.-]+),([\w.-]+),([\w-]+)", content):
        addons.append({
            'name': match.group(1),
            'current_version': match.group(2),
            'target_version': match.group(3),
            'status': match.group(4)
        })

    # Extract errors
    for match in re.finditer(r"ERROR upgrading addon '([\w-]+)'.*?\n(.*?)(?=\n\S)", content, re.DOTALL):
        errors.append(f"{match.group(1)}: {match.group(2).strip()}")

    if not errors:
        for match in re.finditer(r"Error: (.*)", content):
            errors.append(match.group(1))

    return addons, errors

def parse_api_check(content):
    """Parse API version check information"""
    if not content:
        return None
        
    result = {
        'logs': [],
        'summary': 'No information found',
        'report_file': 'Not available'
    }

    # Extract summary
    summary_match = re.search(r"summary=(.*)", content)
    if summary_match:
        result['summary'] = summary_match.group(1)
    elif "No deprecated APIs found" in content:
        result['summary'] = "API Check: No deprecated APIs found."

    # Extract report file
    report_match = re.search(r"Output saved to: ([\w.-]+)", content)
    if report_match:
        result['report_file'] = report_match.group(1)

    # Extract logs
    result['logs'] = [line.strip() for line in content.split('\n') 
                     if line.strip() and not line.startswith(('summary=', 'Report:'))]

    return result

def main():
    # Get input parameters
    input_dir, sleep_duration = get_arguments()
    
    # Optional sleep
    if sleep_duration > 0:
        print(f"Sleeping for {sleep_duration} seconds before processing...")
        time.sleep(sleep_duration)

    # Define required files
    required_files = {
        'cluster': os.path.join(input_dir, 'eks-cluster-summary.txt'),
        'nodegroup': os.path.join(input_dir, 'eks-node-group.log'),
        'addon': os.path.join(input_dir, 'addon-output.txt'),
        'api_check': os.path.join(input_dir, 'api_version_check_output.log')
    }

    # Check files
    missing_files = []
    available_data = {}
    
    for file_type, file_path in required_files.items():
        content = read_file_content(file_path)
        if content is None:
            missing_files.append(file_path)
        else:
            available_data[file_type] = content

    # Fail job if ALL files are missing
    if len(missing_files) == len(required_files):
        print("❌ Error: All required files are missing!")
        print("Missing files:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        sys.exit(1)

    # Show warnings for missing files (but continue)
    if missing_files:
        print("⚠️  Warning: Some files are missing (proceeding with available data):")
        for file_path in missing_files:
            print(f"  - {file_path}")

    # Parse available data
    control_plane = parse_cluster_upgrade(available_data.get('cluster'))
    nodegroups, nodegroup_logs = parse_nodegroup_upgrade(available_data.get('nodegroup'))
    addons, addon_errors = parse_addon_upgrade(available_data.get('addon'))
    api_check = parse_api_check(available_data.get('api_check'))

    # Prepare cluster info
    cluster_info = {}
    if control_plane:
        cluster_info['name'] = control_plane.get('name', 'Unknown')
        if 'region' in control_plane:
            cluster_info['region'] = control_plane['region']

    # Setup Jinja2 environment
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('templates/template.html')

    # Create output directory if needed
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(DEFAULT_OUTPUT_DIR, "eks_upgrade_report.html")

    # Generate HTML report
    with open(report_path, 'w') as f:
        html = template.render(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            cluster_info=cluster_info,
            control_plane=control_plane,
            nodegroups=nodegroups or [],
            nodegroup_logs=nodegroup_logs or [],
            addons=addons or [],
            addon_errors=addon_errors or [],
            api_check=api_check
        )
        f.write(html)

    print(f"✅ Report successfully generated at: {os.path.abspath(report_path)}")

if __name__ == "__main__":
    main()
