import sys
import os
import subprocess

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

# Enable ANSI escape sequences on Windows CMD
os.system('')



class Colors:
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

# Custom config to set a low timeout and 1 retry.
TIMEOUT_CONFIG = Config(
    connect_timeout=2,
    read_timeout=5,
    retries={'max_attempts': 1}
)

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
        regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
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
        if 'AccessDenied' not in str(e):
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
    except Exception:
        pass
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
                print_status("info", f"Deleting S3 Bucket: {name} (clearing contents first)...")
                try:
                    s3_resource = session.resource('s3', config=TIMEOUT_CONFIG)
                    bucket_obj = s3_resource.Bucket(name)
                    bucket_obj.object_versions.delete()
                    bucket_obj.objects.all().delete()
                    s3_client.delete_bucket(Bucket=name)
                    print_status("success", f"Successfully deleted bucket: {name}")
                except Exception as e:
                    print_status("error", f"Failed to delete bucket {name}: {e}")
    except Exception as e:
        if 'AccessDenied' not in str(e):
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
                    print_status("info", f"Deleting Lightsail Instance: {name}", r)
                    ls.delete_instance(instanceName=name)
            
            # Databases
            dbs = ls.get_relational_databases().get('relationalDatabases', [])
            for db in dbs:
                name = db['name']
                print_status("warning", f"Found Lightsail Database: {name}", r)
                found.append({'type': 'Lightsail Database', 'id': name, 'region': r})
                if not dry_run:
                    print_status("info", f"Deleting Lightsail Database: {name}", r)
                    ls.delete_relational_database(relationalDatabaseName=name, skipFinalSnapshot=True)
        except Exception:
            pass
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
    except Exception:
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
                print_status("info", f"Terminating EC2 Instance: {inst_id}", region)
                ec2.terminate_instances(InstanceIds=[inst_id])
    except ClientError as e:
        if 'AuthFailure' in str(e) or 'UnauthorizedOperation' in str(e) or 'OptInRequired' in str(e):
            return found # Skip disabled regions immediately
    except Exception:
        pass

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
                if state == 'in-use':
                    try:
                        ec2.detach_volume(VolumeId=vol_id, Force=True)
                        time.sleep(2)
                    except Exception: pass
                print_status("info", f"Deleting EBS Volume: {vol_id}", region)
                try: ec2.delete_volume(VolumeId=vol_id)
                except Exception: pass
    except Exception: pass

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
                if association_id:
                    try: ec2.disassociate_address(AssociationId=association_id)
                    except Exception: pass
                if alloc_id:
                    print_status("info", f"Releasing Elastic IP: {public_ip}", region)
                    ec2.release_address(AllocationId=alloc_id)
    except Exception: pass

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
                    print_status("info", f"Deleting NAT Gateway: {gw_id}", region)
                    ec2.delete_nat_gateway(NatGatewayId=gw_id)
    except Exception: pass

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
                    print_status("info", f"Deleting VPC Endpoint: {ep_id}...", region)
                    ec2.delete_vpc_endpoints(VpcEndpointIds=[ep_id])
    except Exception: pass

    # 6. Load Balancers
    try:
        elbv2 = session.client('elbv2', region_name=region, config=TIMEOUT_CONFIG)
        for lb in elbv2.describe_load_balancers().get('LoadBalancers', []):
            arn = lb['LoadBalancerArn']
            lb_name = lb['LoadBalancerName']
            print_status("warning", f"Found Load Balancer: {lb_name}", region)
            found.append({'type': 'Load Balancer (v2)', 'id': arn, 'name': lb_name, 'region': region})
            if not dry_run:
                print_status("info", f"Deleting Load Balancer: {lb_name}", region)
                elbv2.delete_load_balancer(LoadBalancerArn=arn)
    except Exception: pass

    # 7. RDS DB Instances
    try:
        for db in rds.describe_db_instances().get('DBInstances', []):
            db_id = db['DBInstanceIdentifier']
            print_status("warning", f"Found RDS Instance: {db_id}", region)
            found.append({'type': 'RDS DB Instance', 'id': db_id, 'region': region})
            if not dry_run:
                if db.get('DeletionProtection', False):
                    try: rds.modify_db_instance(DBInstanceIdentifier=db_id, DeletionProtection=False, ApplyImmediately=True)
                    except Exception: pass
                print_status("info", f"Deleting RDS DB Instance: {db_id}", region)
                rds.delete_db_instance(DBInstanceIdentifier=db_id, SkipFinalSnapshot=True)
    except Exception: pass

    # 8. RDS DB Cluster Snapshots
    try:
        for snap in rds.describe_db_cluster_snapshots().get('DBClusterSnapshots', []):
            if snap['SnapshotType'] == 'manual':
                snap_id = snap['DBClusterSnapshotIdentifier']
                print_status("warning", f"Found RDS Cluster Snapshot: {snap_id}", region)
                found.append({'type': 'RDS Cluster Snapshot', 'id': snap_id, 'region': region})
                if not dry_run:
                    print_status("info", f"Deleting RDS Cluster Snapshot: {snap_id}", region)
                    rds.delete_db_cluster_snapshot(DBClusterSnapshotIdentifier=snap_id)
    except Exception: pass

    # 9. RDS Automated Backups
    try:
        for backup in rds.describe_db_instance_automated_backups().get('DBInstanceAutomatedBackups', []):
            backup_arn = backup['DBInstanceAutomatedBackupsArn']
            print_status("warning", f"Found RDS Retained Automated Backup for DB: {backup['DBInstanceIdentifier']}", region)
            found.append({'type': 'RDS Retained Backup', 'id': backup_arn, 'region': region})
            if not dry_run:
                print_status("info", f"Deleting RDS Retained Backup...", region)
                rds.delete_db_instance_automated_backups(DbInstanceAutomatedBackupsArn=backup_arn)
    except Exception: pass

    # 10. DynamoDB Tables
    try:
        for table in ddb.list_tables().get('TableNames', []):
            print_status("warning", f"Found DynamoDB Table: {table}", region)
            found.append({'type': 'DynamoDB Table', 'id': table, 'region': region})
            if not dry_run:
                print_status("info", f"Deleting DynamoDB Table: {table}", region)
                ddb.delete_table(TableName=table)
    except Exception: pass

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
            return False
            
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
        return True
    except Exception:
        # Return False if access is denied or Cost Explorer is not enabled
        return False

def run_nuke(session, regions, all_resources):
    print_header("Executing Nuke Deletion")
    
    # 1. CloudFront Distributions
    process_cloudfront(session, dry_run=False)
    
    # 2. Global / CloudFront WAFv2
    process_wafv2(session, 'us-east-1', 'CLOUDFRONT', dry_run=False)
    
    # 3. S3 Buckets
    process_s3(session, dry_run=False)
    
    # 4. Lightsail
    process_lightsail(session, dry_run=False)
    
    # 5. Regional Services
    for index, r in enumerate(regions):
        print_status("info", f"[{index + 1}/{len(regions)}] Nuking region: {r}...")
        process_wafv2(session, r, 'REGIONAL', dry_run=False)
        process_regional(session, r, dry_run=False)

def main():
    print_header("AWS Nuke (Dry-Run Scan)")
    
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
    billing_shown = print_billing_dashboard_costs(session)
    if not billing_shown:
        print_status("warning", "Access Denied or Cost Explorer disabled. Skipping billing dashboard cost display.")
        
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
        return
        
    print(f"Total resources found: {Colors.BOLD}{len(all_resources)}{Colors.RESET}")
    print("\nSummary List:")
    for item in all_resources:
        name_str = f" ({item['name']})" if 'name' in item else ""
        region_str = f" in region {item['region']}" if 'region' in item else " (global)"
        print(f"  - {Colors.YELLOW}{item['type']}{Colors.RESET}: {item['id']}{name_str}{region_str}")
        
    print("=" * 60)
    
    # Interactive confirmation prompt
    try:
        confirm = input(f"\n[WARNING] {Colors.BOLD}{Colors.RED}Are you absolutely sure you want to delete all the above resources? (Type 'yes' to nuke): {Colors.RESET}").strip().lower()
        if confirm == 'yes':
            run_nuke(session, regions, all_resources)
            print_header("Nuke Process Complete")
            print(f"{Colors.GREEN}[OK] NUKE PROCESS FINISHED. Some deletions are asynchronous and take time.{Colors.RESET}")
            print("Please re-run the script to verify all resources are successfully deleted.")
            print("=" * 60)
        else:
            print(f"\n{Colors.YELLOW}Nuke cancelled. No resources were deleted.{Colors.RESET}")
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Nuke cancelled.{Colors.RESET}")
        sys.exit(0)

if __name__ == '__main__':
    main()
