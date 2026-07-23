import sys
import os
import subprocess
import threading

# 1. Automate Dependency Installation
try:
    import boto3
except ImportError:
    print("Dependency 'boto3' not found. Installing automatically via pip...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "boto3"])
        import boto3
        print("Dependency 'boto3' installed successfully!")
    except Exception as e:
        print(f"Failed to automatically install 'boto3': {e}")
        print("Please install it manually using: pip install boto3")
        sys.exit(1)

import time
import json
from botocore.exceptions import ClientError
from botocore.config import Config

# Configure stdout encoding for Unicode characters on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Enable ANSI escape sequences on Windows CMD
os.system('')



class Colors:
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    GRAY = '\033[90m'

# Custom config to set a low timeout and 1 retry.
TIMEOUT_CONFIG = Config(
    connect_timeout=2,
    read_timeout=5,
    retries={'max_attempts': 1}
)

# Global tracker for missing IAM permissions
PERMISSION_WARNINGS = set()

# Thread-based loading spinner for CLI operations
class Spinner:
    def __init__(self, message="Working", delay=0.1):
        self.message = message
        self.delay = delay
        # Braille loading spinner characters look extremely professional in modern CLI
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self._running = False
        self._thread = None

    def _spin(self):
        idx = 0
        while self._running:
            # Overwrite line and show spinner
            sys.stdout.write(f"\r {Colors.BLUE}[i]{Colors.RESET} {self.message} {Colors.CYAN}{self.spinner_chars[idx % len(self.spinner_chars)]}{Colors.RESET} ")
            sys.stdout.flush()
            time.sleep(self.delay)
            idx += 1

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        # Clear the spinner line completely
        sys.stdout.write("\r" + " " * (len(self.message) + 15) + "\r")
        sys.stdout.flush()

def print_banner():
    # Large block letters for AWS (CYAN) and TERMINATOR (RED)
    banner_lines = [
        "",
        f" {Colors.CYAN}█████╗ ██╗    ██╗███████╗{Colors.RESET}",
        f" {Colors.CYAN}██╔══██╗██║    ██║██╔════╝{Colors.RESET}",
        f" {Colors.CYAN}███████║██║ █╗ ██║███████╗{Colors.RESET}",
        f" {Colors.CYAN}██╔══██║██║███╗██║╚════██║{Colors.RESET}",
        f" {Colors.CYAN}██║  ██║╚███╔███╔╝███████║{Colors.RESET}",
        f" {Colors.CYAN}╚═╝  ╚═╝ ╚══╝╚══╝ ╚══════╝{Colors.RESET}",
        "",
        f" {Colors.RED}███████╗██████╗  █████╗ ███████╗███████╗██████╗ {Colors.RESET}",
        f" {Colors.RED}██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝██╔══██╗{Colors.RESET}",
        f" {Colors.RED}█████╗  ██████╔╝███████║███████╗█████╗  ██████╔╝{Colors.RESET}",
        f" {Colors.RED}██╔══╝  ██╔══██╗██╔══██║╚════██║██╔══╝  ██╔══██╗{Colors.RESET}",
        f" {Colors.RED}███████╗██║  ██║██║  ██║███████║███████╗██║  ██║{Colors.RESET}",
        f" {Colors.RED}╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝{Colors.RESET}",
        ""
    ]
    
    # Filter out ANSI escapes to calculate clean lengths
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    clean_lines = [ansi_escape.sub('', line) for line in banner_lines]
    max_len = max(len(l) for l in clean_lines)
    # Add a bit of buffer padding
    max_len = max(max_len, 86)
    
    print(f"  {Colors.CYAN}┌{'─' * (max_len + 2)}┐{Colors.RESET}")
    for clean, original in zip(clean_lines, banner_lines):
        padding = " " * (max_len - len(clean))
        # Keep empty lines empty except for borders
        if not clean:
            print(f"  {Colors.CYAN}│{Colors.RESET}{' ' * (max_len + 2)}{Colors.CYAN}│{Colors.RESET}")
        else:
            print(f"  {Colors.CYAN}│{Colors.RESET} {original} {padding}{Colors.CYAN}│{Colors.RESET}")
    print(f"  {Colors.CYAN}└{'─' * (max_len + 2)}┘{Colors.RESET}")

def print_header(title):
    print(f"\n{Colors.BOLD}{Colors.CYAN}" + "=" * 60)
    print(f" {title.upper()} ".center(60, "="))
    print("=" * 60 + f"{Colors.RESET}")

def print_status(status_type, message, region=None):
    region_str = f" [{region}]" if region else ""
    if status_type == "info":
        print(f" {Colors.BLUE}[i]{Colors.RESET}{region_str} {message}")
    elif status_type == "success":
        print(f" {Colors.GREEN}[OK]{Colors.RESET}{region_str} {message}")
    elif status_type == "warning":
        print(f" {Colors.YELLOW}[!]{Colors.RESET}{region_str} {message}")
    elif status_type == "error":
        print(f" {Colors.RED}[X]{Colors.RESET}{region_str} {message}")

# Retrieve credentials either from credentials.json or direct console input
def get_credentials():
    creds_path = "credentials.json"
    if os.path.exists(creds_path):
        try:
            with open(creds_path, 'r') as f:
                creds = json.load(f)
                if "aws_access_key_id" in creds and "aws_secret_access_key" in creds:
                    return creds
        except Exception:
            pass
            
    print_header("AWS Credentials Setup")
    print("No credentials.json file found. Please enter your AWS credentials:")
    try:
        access_key = input("Enter AWS Access Key ID: ").strip()
        secret_key = input("Enter AWS Secret Access Key: ").strip()
        session_token = input("Enter AWS Session Token (Optional, press Enter to skip): ").strip()
        
        if not access_key or not secret_key:
            print(f"{Colors.RED}Error: Both Access Key ID and Secret Access Key are required.{Colors.RESET}")
            sys.exit(1)
            
        return {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "aws_session_token": session_token if session_token else None
        }
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(1)

def get_session(creds):
    return boto3.Session(
        aws_access_key_id=creds["aws_access_key_id"],
        aws_secret_access_key=creds["aws_secret_access_key"],
        aws_session_token=creds.get("aws_session_token")
    )

def get_all_regions(session):
    try:
        ec2 = session.client('ec2', region_name='us-east-1', config=TIMEOUT_CONFIG)
        # Fetch all regions including opt-in regions that are enabled for this account
        response = ec2.describe_regions(AllRegions=True)
        regions = [r['RegionName'] for r in response['Regions'] if r.get('OptInStatus') != 'not-opted-in']
        return regions
    except Exception as e:
        print_status("error", f"Failed to list regions: {e}")
        return ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2', 'ap-south-1', 'eu-central-1', 'eu-west-1', 'eu-west-2']

# CloudFront Distribution manager
def process_cloudfront(session, dry_run=True):
    print_status("info", "Scanning CloudFront Distributions...")
    found = []
    try:
        cf = session.client('cloudfront', config=TIMEOUT_CONFIG)
        response = cf.list_distributions()
        items = response.get('DistributionList', {}).get('Items', [])
        
        for dist in items:
            dist_id = dist['Id']
            status = dist['Status']
            enabled = dist['Enabled']
            web_acl_id = dist.get('WebACLId', '')
            print_status("warning", f"Found CloudFront Distribution: {dist_id} (Enabled: {enabled}, Status: {status}, WebACL: {web_acl_id})")
            found.append({'type': 'CloudFront Distribution', 'id': dist_id, 'web_acl_id': web_acl_id})
            
            if not dry_run:
                # Delete distribution if disabled and deployed
                if not enabled and status == 'Deployed':
                    try:
                        print_status("info", f"Distribution {dist_id} is disabled and deployed. Deleting distribution...")
                        dist_details = cf.get_distribution(Id=dist_id)
                        dist_etag = dist_details['ETag']
                        cf.delete_distribution(Id=dist_id, IfMatch=dist_etag)
                        print_status("success", f"Successfully deleted CloudFront Distribution {dist_id}")
                        continue
                    except Exception as e:
                        print_status("error", f"Failed to delete CloudFront Distribution {dist_id}: {e}")
                        
                # Update config to disable or remove WAF if active
                try:
                    dist_config_res = cf.get_distribution_config(Id=dist_id)
                    config = dist_config_res['DistributionConfig']
                    etag = dist_config_res['ETag']
                    
                    changed = False
                    if config.get('WebACLId') != '':
                        print_status("info", f"Disassociating Web ACL from CloudFront {dist_id}...")
                        config['WebACLId'] = ''
                        changed = True
                    if config['Enabled']:
                        print_status("info", f"Disabling CloudFront Distribution {dist_id}...")
                        config['Enabled'] = False
                        changed = True
                    if changed:
                        cf.update_distribution(DistributionConfig=config, Id=dist_id, IfMatch=etag)
                        print_status("success", f"Successfully updated CloudFront configuration.")
                except Exception as e:
                    print_status("error", f"Failed to update CloudFront Distribution {dist_id}: {e}")
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("CloudFront")
        else:
            print_status("error", f"Error scanning CloudFront: {e}")
    return found

# WAFv2 Manager
def process_wafv2(session, region, scope, dry_run=True):
    waf_region = 'us-east-1' if scope == 'CLOUDFRONT' else region
    found = []
    try:
        waf = session.client('wafv2', region_name=waf_region, config=TIMEOUT_CONFIG)
        response = waf.list_web_acls(Scope=scope)
        web_acls = response.get('WebACLs', [])
        
        for acl in web_acls:
            acl_id = acl['Id']
            name = acl['Name']
            arn = acl['ARN']
            print_status("warning", f"Found WAFv2 Web ACL: {name} (Scope: {scope})", waf_region)
            found.append({'type': 'WAFv2 Web ACL', 'id': acl_id, 'name': name, 'region': waf_region, 'arn': arn, 'scope': scope})
            
            if not dry_run:
                try:
                    acl_details = waf.get_web_acl(Name=name, Id=acl_id, Scope=scope)
                    lock_token = acl_details['LockToken']
                    
                    if scope == 'REGIONAL':
                        associations = waf.list_resources_for_web_acl(WebACLArn=arn).get('ResourceArns', [])
                        for res_arn in associations:
                            print_status("info", f"Disassociating resource {res_arn} from WAF {name}...", waf_region)
                            waf.disassociate_web_acl(ResourceArn=res_arn)
                            
                    print_status("info", f"Deleting WAFv2 Web ACL: {name}...", waf_region)
                    waf.delete_web_acl(Name=name, Id=acl_id, Scope=scope, LockToken=lock_token)
                    print_status("success", f"Successfully deleted WAFv2 Web ACL: {name}", waf_region)
                except Exception as e:
                    print_status("error", f"Failed to delete WAFv2 Web ACL {name}: {e}", waf_region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("WAFv2 (Web Application Firewall)")
    return found

# S3 Buckets manager
def process_s3(session, dry_run=True):
    print_status("info", "Scanning S3 Buckets...")
    found = []
    try:
        s3_client = session.client('s3', config=TIMEOUT_CONFIG)
        response = s3_client.list_buckets()
        buckets = response.get('Buckets', [])
        
        for bucket in buckets:
            name = bucket['Name']
            print_status("warning", f"Found S3 Bucket: {name}")
            found.append({'type': 'S3 Bucket', 'id': name, 'region': 'global'})
            
            if not dry_run:
                spinner = Spinner(f"Deleting S3 Bucket: {name} (clearing contents first)")
                spinner.start()
                try:
                    s3_resource = session.resource('s3', config=TIMEOUT_CONFIG)
                    bucket_obj = s3_resource.Bucket(name)
                    bucket_obj.object_versions.delete()
                    bucket_obj.objects.all().delete()
                    s3_client.delete_bucket(Bucket=name)
                    spinner.stop()
                    print_status("success", f"Successfully deleted bucket: {name}")
                except Exception as e:
                    spinner.stop()
                    print_status("error", f"Failed to delete bucket {name}: {e}")
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("S3 (Simple Storage Service)")
        else:
            print_status("error", f"Failed to scan S3: {e}")
    return found

# Lightsail Manager
def process_lightsail(session, dry_run=True):
    print_status("info", "Scanning Lightsail resources...")
    lightsail_regions = ['us-east-1', 'us-east-2', 'us-west-2', 'eu-west-1', 'eu-west-2', 'eu-central-1', 'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1', 'ap-northeast-2', 'ap-south-1', 'ca-central-1']
    found = []
    
    for r in lightsail_regions:
        try:
            ls = session.client('lightsail', region_name=r, config=TIMEOUT_CONFIG)
            
            # Instances
            instances = ls.get_instances().get('instances', [])
            for inst in instances:
                name = inst['name']
                print_status("warning", f"Found Lightsail Instance: {name}", r)
                found.append({'type': 'Lightsail Instance', 'id': name, 'region': r})
                if not dry_run:
                    spinner = Spinner(f"Deleting Lightsail Instance: {name}")
                    spinner.start()
                    try:
                        ls.delete_instance(instanceName=name)
                        spinner.stop()
                        print_status("success", f"Successfully deleted Lightsail Instance: {name}", r)
                    except Exception as e:
                        spinner.stop()
                        print_status("error", f"Failed to delete Lightsail Instance {name}: {e}", r)
            
            # Databases
            dbs = ls.get_relational_databases().get('relationalDatabases', [])
            for db in dbs:
                name = db['name']
                print_status("warning", f"Found Lightsail Database: {name}", r)
                found.append({'type': 'Lightsail Database', 'id': name, 'region': r})
                if not dry_run:
                    spinner = Spinner(f"Deleting Lightsail Database: {name}")
                    spinner.start()
                    try:
                        ls.delete_relational_database(relationalDatabaseName=name, skipFinalSnapshot=True)
                        spinner.stop()
                        print_status("success", f"Successfully deleted Lightsail Database: {name}", r)
                    except Exception as e:
                        spinner.stop()
                        print_status("error", f"Failed to delete Lightsail Database {name}: {e}", r)
        except Exception as e:
            if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
                PERMISSION_WARNINGS.add("Lightsail")
    return found

# Helper to extract Name tag from resource tags list
def get_name_from_tags(tags):
    if not tags:
        return ""
    for tag in tags:
        if tag.get('Key') == 'Name':
            return tag.get('Value', '')
    return ""

# Regional resource manager
def process_regional(session, region, dry_run=True):
    found = []
    try:
        ec2 = session.client('ec2', region_name=region, config=TIMEOUT_CONFIG)
        rds = session.client('rds', region_name=region, config=TIMEOUT_CONFIG)
        ddb = session.client('dynamodb', region_name=region, config=TIMEOUT_CONFIG)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("Regional APIs (EC2/RDS/DynamoDB initialization)")
        return found

    # 1. EC2 Instances
    try:
        instances = []
        paginator = ec2.get_paginator('describe_instances')
        for page in paginator.paginate():
            for r in page.get('Reservations', []):
                for inst in r.get('Instances', []):
                    if inst['State']['Name'] != 'terminated':
                        instances.append(inst)
                        
        for inst in instances:
            inst_id = inst['InstanceId']
            name = get_name_from_tags(inst.get('Tags', []))
            print_name = f" ({name})" if name else ""
            print_status("warning", f"Found EC2 Instance: {inst_id}{print_name}", region)
            
            res_item = {'type': 'EC2 Instance', 'id': inst_id, 'region': region}
            if name:
                res_item['name'] = name
            found.append(res_item)
            
            if not dry_run:
                spinner = Spinner(f"Terminating EC2 Instance: {inst_id}")
                spinner.start()
                try:
                    ec2.terminate_instances(InstanceIds=[inst_id])
                    spinner.stop()
                    print_status("success", f"Successfully terminated EC2 Instance: {inst_id}", region)
                except Exception as e:
                    spinner.stop()
                    print_status("error", f"Failed to terminate EC2 Instance {inst_id}: {e}", region)
    except ClientError as e:
        if 'AuthFailure' in str(e) or 'UnauthorizedOperation' in str(e) or 'OptInRequired' in str(e):
            if 'UnauthorizedOperation' in str(e):
                PERMISSION_WARNINGS.add("EC2 (Elastic Compute Cloud)")
            return found # Skip disabled regions immediately
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("EC2 (Elastic Compute Cloud)")

    # 2. EBS Volumes
    try:
        volumes = ec2.describe_volumes().get('Volumes', [])
        for vol in volumes:
            vol_id = vol['VolumeId']
            state = vol['State']
            name = get_name_from_tags(vol.get('Tags', []))
            print_name = f" ({name})" if name else ""
            print_status("warning", f"Found EBS Volume: {vol_id}{print_name} ({state})", region)
            
            res_item = {'type': 'EBS Volume', 'id': vol_id, 'region': region}
            if name:
                res_item['name'] = name
            found.append(res_item)
            
            if not dry_run:
                spinner = Spinner(f"Deleting EBS Volume: {vol_id}")
                spinner.start()
                try:
                    if state == 'in-use':
                        try:
                            ec2.detach_volume(VolumeId=vol_id, Force=True)
                            time.sleep(2)
                        except Exception: pass
                    ec2.delete_volume(VolumeId=vol_id)
                    spinner.stop()
                    print_status("success", f"Successfully deleted EBS Volume: {vol_id}", region)
                except Exception as e:
                    spinner.stop()
                    print_status("error", f"Failed to delete EBS Volume {vol_id}: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("EC2 (Elastic Block Store Volumes)")

    # 3. Elastic IPs
    try:
        eips = ec2.describe_addresses().get('Addresses', [])
        for ip in eips:
            alloc_id = ip.get('AllocationId')
            public_ip = ip.get('PublicIp')
            association_id = ip.get('AssociationId')
            name = get_name_from_tags(ip.get('Tags', []))
            print_name = f" ({name})" if name else ""
            print_status("warning", f"Found Elastic IP: {public_ip}{print_name}", region)
            
            res_item = {'type': 'Elastic IP', 'id': public_ip, 'region': region}
            if name:
                res_item['name'] = name
            found.append(res_item)
            
            if not dry_run:
                spinner = Spinner(f"Releasing Elastic IP: {public_ip}")
                spinner.start()
                try:
                    if association_id:
                        try: ec2.disassociate_address(AssociationId=association_id)
                        except Exception: pass
                    if alloc_id:
                        ec2.release_address(AllocationId=alloc_id)
                    spinner.stop()
                    print_status("success", f"Successfully released Elastic IP: {public_ip}", region)
                except Exception as e:
                    spinner.stop()
                    print_status("error", f"Failed to release Elastic IP {public_ip}: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("EC2 (Elastic IP Addresses)")

    # 4. NAT Gateways
    try:
        nat_gws = ec2.describe_nat_gateways().get('NatGateways', [])
        for gw in nat_gws:
            if gw['State'] not in ['deleted', 'deleting']:
                gw_id = gw['NatGatewayId']
                name = get_name_from_tags(gw.get('Tags', []))
                print_name = f" ({name})" if name else ""
                print_status("warning", f"Found NAT Gateway: {gw_id}{print_name}", region)
                
                res_item = {'type': 'NAT Gateway', 'id': gw_id, 'region': region}
                if name:
                    res_item['name'] = name
                found.append(res_item)
                
                if not dry_run:
                    spinner = Spinner(f"Deleting NAT Gateway: {gw_id}")
                    spinner.start()
                    try:
                        ec2.delete_nat_gateway(NatGatewayId=gw_id)
                        spinner.stop()
                        print_status("success", f"Successfully deleted NAT Gateway: {gw_id}", region)
                    except Exception as e:
                        spinner.stop()
                        print_status("error", f"Failed to delete NAT Gateway {gw_id}: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("EC2 (NAT Gateways)")

    # 5. VPC Endpoints
    try:
        endpoints = ec2.describe_vpc_endpoints().get('VpcEndpoints', [])
        for ep in endpoints:
            if ep['State'] != 'deleted':
                ep_id = ep['VpcEndpointId']
                name = get_name_from_tags(ep.get('Tags', []))
                print_name = f" ({name})" if name else ""
                print_status("warning", f"Found VPC Endpoint: {ep_id}{print_name}", region)
                
                res_item = {'type': 'VPC Endpoint', 'id': ep_id, 'region': region}
                if name:
                    res_item['name'] = name
                found.append(res_item)
                
                if not dry_run:
                    spinner = Spinner(f"Deleting VPC Endpoint: {ep_id}")
                    spinner.start()
                    try:
                        ec2.delete_vpc_endpoints(VpcEndpointIds=[ep_id])
                        spinner.stop()
                        print_status("success", f"Successfully deleted VPC Endpoint: {ep_id}", region)
                    except Exception as e:
                        spinner.stop()
                        print_status("error", f"Failed to delete VPC Endpoint {ep_id}: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("EC2 (VPC Endpoints)")

    # 6. Load Balancers
    try:
        elbv2 = session.client('elbv2', region_name=region, config=TIMEOUT_CONFIG)
        for lb in elbv2.describe_load_balancers().get('LoadBalancers', []):
            arn = lb['LoadBalancerArn']
            lb_name = lb['LoadBalancerName']
            print_status("warning", f"Found Load Balancer: {lb_name}", region)
            found.append({'type': 'Load Balancer (v2)', 'id': arn, 'name': lb_name, 'region': region})
            if not dry_run:
                spinner = Spinner(f"Deleting Load Balancer: {lb_name}")
                spinner.start()
                try:
                    elbv2.delete_load_balancer(LoadBalancerArn=arn)
                    spinner.stop()
                    print_status("success", f"Successfully deleted Load Balancer: {lb_name}", region)
                except Exception as e:
                    spinner.stop()
                    print_status("error", f"Failed to delete Load Balancer {lb_name}: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("ELB (Elastic Load Balancing)")

    # 7. RDS DB Instances
    try:
        for db in rds.describe_db_instances().get('DBInstances', []):
            db_id = db['DBInstanceIdentifier']
            print_status("warning", f"Found RDS Instance: {db_id}", region)
            found.append({'type': 'RDS DB Instance', 'id': db_id, 'region': region})
            if not dry_run:
                spinner = Spinner(f"Deleting RDS DB Instance: {db_id}")
                spinner.start()
                try:
                    if db.get('DeletionProtection', False):
                        try: rds.modify_db_instance(DBInstanceIdentifier=db_id, DeletionProtection=False, ApplyImmediately=True)
                        except Exception: pass
                    rds.delete_db_instance(DBInstanceIdentifier=db_id, SkipFinalSnapshot=True)
                    spinner.stop()
                    print_status("success", f"Successfully deleted RDS DB Instance: {db_id}", region)
                except Exception as e:
                    spinner.stop()
                    print_status("error", f"Failed to delete RDS DB Instance {db_id}: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("RDS (Relational Database Service)")

    # 8. RDS DB Cluster Snapshots
    try:
        for snap in rds.describe_db_cluster_snapshots().get('DBClusterSnapshots', []):
            if snap['SnapshotType'] == 'manual':
                snap_id = snap['DBClusterSnapshotIdentifier']
                print_status("warning", f"Found RDS Cluster Snapshot: {snap_id}", region)
                found.append({'type': 'RDS Cluster Snapshot', 'id': snap_id, 'region': region})
                if not dry_run:
                    spinner = Spinner(f"Deleting RDS Cluster Snapshot: {snap_id}")
                    spinner.start()
                    try:
                        rds.delete_db_cluster_snapshot(DBClusterSnapshotIdentifier=snap_id)
                        spinner.stop()
                        print_status("success", f"Successfully deleted RDS Cluster Snapshot: {snap_id}", region)
                    except Exception as e:
                        spinner.stop()
                        print_status("error", f"Failed to delete RDS Cluster Snapshot {snap_id}: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("RDS (Relational Database Service)")

    # 9. RDS Automated Backups
    try:
        for backup in rds.describe_db_instance_automated_backups().get('DBInstanceAutomatedBackups', []):
            backup_arn = backup['DBInstanceAutomatedBackupsArn']
            print_status("warning", f"Found RDS Retained Automated Backup for DB: {backup['DBInstanceIdentifier']}", region)
            found.append({'type': 'RDS Retained Backup', 'id': backup_arn, 'region': region})
            if not dry_run:
                spinner = Spinner(f"Deleting RDS Retained Backup")
                spinner.start()
                try:
                    rds.delete_db_instance_automated_backups(DbInstanceAutomatedBackupsArn=backup_arn)
                    spinner.stop()
                    print_status("success", f"Successfully deleted RDS Retained Backup", region)
                except Exception as e:
                    spinner.stop()
                    print_status("error", f"Failed to delete RDS Retained Backup: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("RDS (Relational Database Service)")

    # 10. DynamoDB Tables
    try:
        for table in ddb.list_tables().get('TableNames', []):
            print_status("warning", f"Found DynamoDB Table: {table}", region)
            found.append({'type': 'DynamoDB Table', 'id': table, 'region': region})
            if not dry_run:
                spinner = Spinner(f"Deleting DynamoDB Table: {table}")
                spinner.start()
                try:
                    ddb.delete_table(TableName=table)
                    spinner.stop()
                    print_status("success", f"Successfully deleted DynamoDB Table: {table}", region)
                except Exception as e:
                    spinner.stop()
                    print_status("error", f"Failed to delete DynamoDB Table {table}: {e}", region)
    except Exception as e:
        if 'AccessDenied' in str(e) or 'UnauthorizedOperation' in str(e):
            PERMISSION_WARNINGS.add("DynamoDB")

    return found

# Query the real Cost Explorer dashboard costs
def print_billing_dashboard_costs(session):
    try:
        # Cost Explorer requires regional endpoints (us-east-1 for pricing/CE API queries)
        ce = session.client('ce', region_name='us-east-1', config=TIMEOUT_CONFIG)
        
        from datetime import datetime, timedelta, timezone
        end_date = datetime.now(timezone.utc).date()
        # Set start date to the beginning of the current month
        start_date = end_date.replace(day=1)
        if start_date == end_date:
            start_date = start_date - timedelta(days=1)
            
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
        )
        
        results = response.get('ResultsByTime', [])
        if not results:
            return False, "No results returned from Cost Explorer API."
            
        print_header("Accrued Billing Dashboard Cost (Current Month)")
        total_cost = 0.0
        groups = results[0].get('Groups', [])
        
        for group in groups:
            service_name = group['Keys'][0]
            amount = float(group['Metrics']['UnblendedCost']['Amount'])
            if amount > 0.01:
                total_cost += amount
                print(f"  - {Colors.YELLOW}{service_name}{Colors.RESET}: ${amount:.2f}")
                
        print("-" * 60)
        print(f"{Colors.BOLD}{Colors.GREEN}TOTAL CURRENT MONTH BILL: ${total_cost:.2f}{Colors.RESET}")
        print(f"\n{Colors.CYAN}[i] Note: The billing dashboard shows cumulative accrued costs for the current month.{Colors.RESET}")
        print(f"{Colors.CYAN}    Once deleted, resources stop accumulating costs, but their past accrued charges{Colors.RESET}")
        print(f"{Colors.CYAN}    will remain visible on your bill history until the billing cycle ends.{Colors.RESET}")
        print("=" * 60)
        return True, ""
    except Exception as e:
        # Return False and the exception details
        return False, str(e)

def parse_resource_selection(user_input, total_count):
    cleaned = user_input.strip().lower()
    if not cleaned or cleaned == 'cancel':
        return None
    if cleaned == 'all':
        return list(range(total_count))
        
    selected_indices = set()
    parts = cleaned.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            range_parts = part.split('-')
            if len(range_parts) != 2:
                raise ValueError(f"Invalid range format: '{part}'")
            try:
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
            except ValueError:
                raise ValueError(f"Non-numeric values in range: '{part}'")
                
            if start > end:
                raise ValueError(f"Start index cannot be greater than end index in range: '{part}'")
            if start < 1 or end > total_count:
                raise ValueError(f"Range {start}-{end} out of bounds (1-{total_count})")
                
            for i in range(start, end + 1):
                selected_indices.add(i - 1)
        else:
            try:
                val = int(part)
            except ValueError:
                raise ValueError(f"Invalid number or format: '{part}'")
            if val < 1 or val > total_count:
                raise ValueError(f"Resource index {val} is out of bounds (1-{total_count})")
            selected_indices.add(val - 1)
            
    return sorted(list(selected_indices))

def delete_single_resource(session, item):
    res_type = item.get('type')
    res_id = item.get('id')
    region = item.get('region', 'us-east-1')
    name = item.get('name', '')
    name_str = f" ({name})" if name else ""

    spinner = Spinner(f"Deleting {res_type}: {res_id}{name_str}")
    spinner.start()

    try:
        if res_type == 'CloudFront Distribution':
            cf = session.client('cloudfront', config=TIMEOUT_CONFIG)
            dist_details = cf.get_distribution(Id=res_id)
            etag = dist_details['ETag']
            config = dist_details['Distribution']['DistributionConfig']
            status = dist_details['Distribution']['Status']
            enabled = config['Enabled']

            if not enabled and status == 'Deployed':
                cf.delete_distribution(Id=res_id, IfMatch=etag)
                spinner.stop()
                print_status("success", f"Successfully deleted CloudFront Distribution {res_id}")
            else:
                changed = False
                if config.get('WebACLId') != '':
                    config['WebACLId'] = ''
                    changed = True
                if config['Enabled']:
                    config['Enabled'] = False
                    changed = True
                if changed:
                    cf.update_distribution(DistributionConfig=config, Id=res_id, IfMatch=etag)
                    spinner.stop()
                    print_status("success", f"Disabled CloudFront Distribution {res_id}. (Note: Distribution must be deployed before full deletion)")
                else:
                    spinner.stop()
                    print_status("info", f"CloudFront Distribution {res_id} is disabling. Please re-run later to complete deletion.")

        elif res_type == 'WAFv2 Web ACL':
            waf_region = 'us-east-1' if item.get('scope') == 'CLOUDFRONT' else region
            waf = session.client('wafv2', region_name=waf_region, config=TIMEOUT_CONFIG)
            acl_details = waf.get_web_acl(Name=item['name'], Id=res_id, Scope=item['scope'])
            lock_token = acl_details['LockToken']
            if item.get('scope') == 'REGIONAL':
                try:
                    associations = waf.list_resources_for_web_acl(WebACLArn=item['arn']).get('ResourceArns', [])
                    for res_arn in associations:
                        waf.disassociate_web_acl(ResourceArn=res_arn)
                except Exception:
                    pass
            waf.delete_web_acl(Name=item['name'], Id=res_id, Scope=item['scope'], LockToken=lock_token)
            spinner.stop()
            print_status("success", f"Successfully deleted WAFv2 Web ACL: {item['name']}", waf_region)

        elif res_type == 'S3 Bucket':
            s3_client = session.client('s3', config=TIMEOUT_CONFIG)
            s3_resource = session.resource('s3', config=TIMEOUT_CONFIG)
            bucket_obj = s3_resource.Bucket(res_id)
            bucket_obj.object_versions.delete()
            bucket_obj.objects.all().delete()
            s3_client.delete_bucket(Bucket=res_id)
            spinner.stop()
            print_status("success", f"Successfully deleted S3 Bucket: {res_id}")

        elif res_type == 'Lightsail Instance':
            ls = session.client('lightsail', region_name=region, config=TIMEOUT_CONFIG)
            ls.delete_instance(instanceName=res_id)
            spinner.stop()
            print_status("success", f"Successfully deleted Lightsail Instance: {res_id}", region)

        elif res_type == 'Lightsail Database':
            ls = session.client('lightsail', region_name=region, config=TIMEOUT_CONFIG)
            ls.delete_relational_database(relationalDatabaseName=res_id, skipFinalSnapshot=True)
            spinner.stop()
            print_status("success", f"Successfully deleted Lightsail Database: {res_id}", region)

        elif res_type == 'EC2 Instance':
            ec2 = session.client('ec2', region_name=region, config=TIMEOUT_CONFIG)
            ec2.terminate_instances(InstanceIds=[res_id])
            spinner.stop()
            print_status("success", f"Successfully terminated EC2 Instance: {res_id}", region)

        elif res_type == 'EBS Volume':
            ec2 = session.client('ec2', region_name=region, config=TIMEOUT_CONFIG)
            try:
                vol_info = ec2.describe_volumes(VolumeIds=[res_id]).get('Volumes', [])
                if vol_info and vol_info[0]['State'] == 'in-use':
                    ec2.detach_volume(VolumeId=res_id, Force=True)
                    time.sleep(2)
            except Exception:
                pass
            ec2.delete_volume(VolumeId=res_id)
            spinner.stop()
            print_status("success", f"Successfully deleted EBS Volume: {res_id}", region)

        elif res_type == 'Elastic IP':
            ec2 = session.client('ec2', region_name=region, config=TIMEOUT_CONFIG)
            addresses = ec2.describe_addresses(PublicIps=[res_id]).get('Addresses', [])
            if addresses:
                addr = addresses[0]
                if addr.get('AssociationId'):
                    try:
                        ec2.disassociate_address(AssociationId=addr['AssociationId'])
                    except Exception:
                        pass
                if addr.get('AllocationId'):
                    ec2.release_address(AllocationId=addr['AllocationId'])
            spinner.stop()
            print_status("success", f"Successfully released Elastic IP: {res_id}", region)

        elif res_type == 'NAT Gateway':
            ec2 = session.client('ec2', region_name=region, config=TIMEOUT_CONFIG)
            ec2.delete_nat_gateway(NatGatewayId=res_id)
            spinner.stop()
            print_status("success", f"Successfully deleted NAT Gateway: {res_id}", region)

        elif res_type == 'VPC Endpoint':
            ec2 = session.client('ec2', region_name=region, config=TIMEOUT_CONFIG)
            ec2.delete_vpc_endpoints(VpcEndpointIds=[res_id])
            spinner.stop()
            print_status("success", f"Successfully deleted VPC Endpoint: {res_id}", region)

        elif res_type == 'Load Balancer (v2)':
            elbv2 = session.client('elbv2', region_name=region, config=TIMEOUT_CONFIG)
            elbv2.delete_load_balancer(LoadBalancerArn=res_id)
            spinner.stop()
            print_status("success", f"Successfully deleted Load Balancer: {name or res_id}", region)

        elif res_type == 'RDS DB Instance':
            rds = session.client('rds', region_name=region, config=TIMEOUT_CONFIG)
            try:
                rds.modify_db_instance(DBInstanceIdentifier=res_id, DeletionProtection=False, ApplyImmediately=True)
            except Exception:
                pass
            rds.delete_db_instance(DBInstanceIdentifier=res_id, SkipFinalSnapshot=True)
            spinner.stop()
            print_status("success", f"Successfully deleted RDS DB Instance: {res_id}", region)

        elif res_type == 'RDS Cluster Snapshot':
            rds = session.client('rds', region_name=region, config=TIMEOUT_CONFIG)
            rds.delete_db_cluster_snapshot(DBClusterSnapshotIdentifier=res_id)
            spinner.stop()
            print_status("success", f"Successfully deleted RDS Cluster Snapshot: {res_id}", region)

        elif res_type == 'RDS Retained Backup':
            rds = session.client('rds', region_name=region, config=TIMEOUT_CONFIG)
            rds.delete_db_instance_automated_backups(DbInstanceAutomatedBackupsArn=res_id)
            spinner.stop()
            print_status("success", f"Successfully deleted RDS Retained Backup", region)

        elif res_type == 'DynamoDB Table':
            ddb = session.client('dynamodb', region_name=region, config=TIMEOUT_CONFIG)
            ddb.delete_table(TableName=res_id)
            spinner.stop()
            print_status("success", f"Successfully deleted DynamoDB Table: {res_id}", region)

        else:
            spinner.stop()
            print_status("warning", f"Unknown resource type '{res_type}' for {res_id}")

    except Exception as e:
        spinner.stop()
        print_status("error", f"Failed to delete {res_type} {res_id}: {e}", region)

def delete_selected_resources(session, items_to_delete):
    print_header("Executing Resource Deletion")
    for idx, item in enumerate(items_to_delete, 1):
        print(f"\n{Colors.BOLD}[{idx}/{len(items_to_delete)}]{Colors.RESET}")
        delete_single_resource(session, item)

def run_nuke(session, regions, all_resources):
    delete_selected_resources(session, all_resources)

def main():
    print_banner()
    
    creds = get_credentials()
    session = get_session(creds)
    
    # Test authentication
    try:
        sts = session.client('sts', config=TIMEOUT_CONFIG)
        identity = sts.get_caller_identity()
        print(f"{Colors.GREEN}Successfully authenticated as:{Colors.RESET}")
        print(f"  Account ID: {identity['Account']}")
        print(f"  User ARN: {identity['Arn']}")
    except Exception as e:
        print_status("error", f"Authentication failed: {e}")
        sys.exit(1)
        
    # Attempt to print real AWS billing dashboard details
    billing_shown, billing_error = print_billing_dashboard_costs(session)
    if not billing_shown:
        if billing_error and "DataUnavailableException" in billing_error:
            print_status("info", "AWS Cost Explorer is currently initializing or has no data history yet.")
            print(f"     {Colors.CYAN}Note: It can take up to 24 hours for AWS to populate Cost Explorer data after activation.{Colors.RESET}")
            print(f"     {Colors.CYAN}The script will automatically proceed with scanning active resources...{Colors.RESET}")
        else:
            print_status("warning", "Access Denied or Cost Explorer disabled. Skipping billing dashboard cost display.")
            if billing_error:
                print(f"     {Colors.RED}AWS Error Details: {billing_error}{Colors.RESET}")
            print(f"     {Colors.CYAN}How to resolve this in 2 simple steps:{Colors.RESET}")
            print(f"       1. Activate IAM Billing Access (must be done by AWS Root User account) at:{Colors.RESET}")
            print(f"          https://console.aws.amazon.com/billing/home?#/account{Colors.RESET}")
            print(f"       2. Attach the 'AWSBillingReadOnlyAccess' managed policy to your IAM User/Role at:{Colors.RESET}")
            print(f"          https://console.aws.amazon.com/iam/home?#/users{Colors.RESET}")
            
            try:
                proceed = input(f"\n{Colors.YELLOW}Would you like to proceed with the scan without billing details? (yes/no): {Colors.RESET}").strip().lower()
                if proceed != 'yes':
                    print(f"\n{Colors.YELLOW}Exiting. Please configure Cost Explorer permissions and run again.{Colors.RESET}")
                    sys.exit(0)
            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}Exiting.{Colors.RESET}")
                sys.exit(0)
        
    print("\nRetrieving AWS regions...")
    regions = get_all_regions(session)
    print_status("info", f"Found {len(regions)} regions to scan.")
    
    # Run Dry-Run scan first
    all_resources = []
    
    print_header("Scanning Global Services")
    all_resources.extend(process_cloudfront(session, dry_run=True))
    all_resources.extend(process_wafv2(session, 'us-east-1', 'CLOUDFRONT', dry_run=True))
    all_resources.extend(process_s3(session, dry_run=True))
    all_resources.extend(process_lightsail(session, dry_run=True))
    
    print_header("Scanning Regional Services")
    for index, r in enumerate(regions):
        print_status("info", f"[{index + 1}/{len(regions)}] Scanning region: {r}...")
        res_waf = process_wafv2(session, r, 'REGIONAL', dry_run=True)
        all_resources.extend(res_waf)
        res_reg = process_regional(session, r, dry_run=True)
        all_resources.extend(res_reg)
        
    # Summary of findings
    print_header("Scan Summary")
    if not all_resources:
        print(f"{Colors.GREEN}No active billing resources found in this AWS account.{Colors.RESET}")
    else:
        print(f"Total resources found: {Colors.BOLD}{len(all_resources)}{Colors.RESET}")
        print("\nSummary List:")
        for index, item in enumerate(all_resources, 1):
            name_str = f" ({item['name']})" if 'name' in item else ""
            region_str = f" in region {item['region']}" if 'region' in item else " (global)"
            print(f"  [{Colors.CYAN}{index}{Colors.RESET}] {Colors.YELLOW}{item['type']}{Colors.RESET}: {item['id']}{name_str}{region_str}")
        
    print("=" * 60)

    # Print permission warnings if any occurred
    if PERMISSION_WARNINGS:
        print_header("Scan Warnings (Missing Permissions)")
        print(f" {Colors.YELLOW}[!]{Colors.RESET} Insufficient permissions detected for the following services:")
        for service in sorted(PERMISSION_WARNINGS):
            print(f"     - {service}")
        print(f"\n {Colors.BLUE}[i]{Colors.RESET} Note: Active resources under these services could not be scanned")
        print("     or deleted. To resolve these errors, refer to the detailed guide in:")
        print(f"     {Colors.CYAN}PERMISSIONS.md{Colors.RESET} or ask your AI coding assistant to generate the correct policies.")
        print("=" * 60)

    if not all_resources:
        return
    
    # Interactive Post-Scan Deletion Menu
    print_header("Deletion Options")
    print("  1. Nuke ALL resources (Delete every resource listed above)")
    print("  2. Select specific resources to delete manually")
    print("  3. Cancel and exit (No resources will be deleted)")

    try:
        choice = input(f"\n{Colors.BOLD}{Colors.CYAN}Select an option (1-3): {Colors.RESET}").strip()
        
        if choice == '1':
            print(f"\n{Colors.BOLD}{Colors.RED}[WARNING] You have selected to NUKE ALL {len(all_resources)} resources!{Colors.RESET}")
            confirm = input(f"{Colors.YELLOW}Are you absolutely sure? (Type 'yes' to nuke all): {Colors.RESET}").strip().lower()
            if confirm == 'yes':
                delete_selected_resources(session, all_resources)
                print_header("Nuke Process Complete")
                print(f"{Colors.GREEN}[OK] NUKE PROCESS FINISHED. Some deletions are asynchronous and take time.{Colors.RESET}")
                print("Please re-run the script to verify all resources are successfully deleted.")
                print("=" * 60)
            else:
                print(f"\n{Colors.YELLOW}Nuke cancelled. No resources were deleted.{Colors.RESET}")

        elif choice == '2':
            print_header("Manual Resource Selection")
            for idx, item in enumerate(all_resources, 1):
                name_str = f" ({item['name']})" if 'name' in item else ""
                region_str = f" in region {item['region']}" if 'region' in item else " (global)"
                print(f"  [{Colors.CYAN}{idx}{Colors.RESET}] {Colors.YELLOW}{item['type']}{Colors.RESET}: {item['id']}{name_str}{region_str}")

            print(f"\n{Colors.CYAN}Enter resource numbers to delete (e.g., '1, 3, 5-8', 'all', or 'cancel'):{Colors.RESET}")
            while True:
                sel_input = input(f"{Colors.BOLD}> {Colors.RESET}").strip()
                if not sel_input or sel_input.lower() == 'cancel':
                    print(f"\n{Colors.YELLOW}Manual selection cancelled. No resources deleted.{Colors.RESET}")
                    return
                try:
                    selected_indices = parse_resource_selection(sel_input, len(all_resources))
                    if selected_indices is None:
                        print(f"\n{Colors.YELLOW}Manual selection cancelled. No resources deleted.{Colors.RESET}")
                        return
                    break
                except ValueError as ve:
                    print(f"  {Colors.RED}[Error] {ve}. Please try again.{Colors.RESET}")

            selected_items = [all_resources[i] for i in selected_indices]
            print_header(f"Confirm Deletion ({len(selected_items)} Selected Item{'s' if len(selected_items) > 1 else ''})")
            for item in selected_items:
                name_str = f" ({item['name']})" if 'name' in item else ""
                region_str = f" in region {item['region']}" if 'region' in item else " (global)"
                print(f"  - {Colors.YELLOW}{item['type']}{Colors.RESET}: {item['id']}{name_str}{region_str}")

            confirm = input(f"\n{Colors.BOLD}{Colors.RED}Are you sure you want to delete these {len(selected_items)} resource(s)? (Type 'yes' to proceed): {Colors.RESET}").strip().lower()
            if confirm == 'yes':
                delete_selected_resources(session, selected_items)
                print_header("Deletion Process Complete")
                print(f"{Colors.GREEN}[OK] DELETION PROCESS FINISHED. Some deletions are asynchronous and take time.{Colors.RESET}")
                print("Please re-run the script to verify resources are successfully deleted.")
                print("=" * 60)
            else:
                print(f"\n{Colors.YELLOW}Deletion cancelled. No resources were deleted.{Colors.RESET}")

        else:
            print(f"\n{Colors.YELLOW}Operation cancelled. No resources were deleted.{Colors.RESET}")

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Operation cancelled.{Colors.RESET}")
        sys.exit(0)

if __name__ == '__main__':
    main()
