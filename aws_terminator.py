import sys
import os
import json
import time
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

# Custom config to set a low timeout and 1 retry.
TIMEOUT_CONFIG = Config(
    connect_timeout=2,
    read_timeout=5,
    retries={'max_attempts': 1}
)

# Approximate baseline monthly costs for common AWS resources (USD)
PRICING_ESTIMATES = {
    'NAT Gateway': 32.40,            # ~$0.045/hour
    'Elastic IP': 3.60,              # ~$0.005/hour (unattached/all public IPs)
    'Load Balancer (v2)': 16.20,     # ~$0.0225/hour baseline
    'Load Balancer (Classic)': 16.20,# ~$0.0225/hour baseline
    'VPC Endpoint': 7.20,            # ~$0.01/hour baseline
    'VPN Connection': 36.00,         # ~$0.05/hour
    'VPN Gateway': 0.00,             # Gateway itself is free, connection charges apply
    'Transit Gateway': 36.00,        # ~$0.05/hour attachment baseline
    'WAFv2 Web ACL': 5.00,           # $5.00/month baseline (plus $1.00 per rule)
    'EC2 Instance': 8.50,            # General estimate for t3.micro/small instance baseline
    'RDS DB Instance': 15.00,        # General estimate for t3.micro database baseline
    'RDS Cluster Snapshot': 0.10,    # Est. per-GB backup storage cost
    'RDS Retained Backup': 0.10,     # Est. per-GB backup storage cost
    'Lightsail Instance': 3.50,      # Smallest Lightsail instance baseline
    'Lightsail Database': 15.00,     # Smallest Lightsail database baseline
    'S3 Bucket': 0.00,               # Storage dependent, baseline shown as $0.00
    'DynamoDB Table': 0.50,          # Est. baseline capacity costs if not free-tier
    'Customer Gateway': 0.00,
    'CloudFront Distribution': 0.00  # Usage dependent (no baseline flat fee)
}

def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title.upper()} ".center(60, "="))
    print("=" * 60)

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
            print("Error: Both Access Key ID and Secret Access Key are required.")
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
        print(f"Failed to list regions: {e}")
        return ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2', 'ap-south-1', 'eu-central-1', 'eu-west-1', 'eu-west-2']

# CloudFront Distribution manager
def process_cloudfront(session, dry_run=True):
    print("Scanning CloudFront Distributions...")
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
            print(f"  Found CloudFront Distribution: {dist_id} (Enabled: {enabled}, Status: {status}, WebACL: {web_acl_id})")
            found.append({'type': 'CloudFront Distribution', 'id': dist_id, 'web_acl_id': web_acl_id})
            
            if not dry_run:
                # Delete distribution if disabled and deployed
                if not enabled and status == 'Deployed':
                    try:
                        print(f"    Distribution {dist_id} is disabled and deployed. Deleting distribution...")
                        dist_details = cf.get_distribution(Id=dist_id)
                        dist_etag = dist_details['ETag']
                        cf.delete_distribution(Id=dist_id, IfMatch=dist_etag)
                        print(f"    Successfully deleted CloudFront Distribution {dist_id}")
                        continue
                    except Exception as e:
                        print(f"    Failed to delete CloudFront Distribution {dist_id}: {e}")
                        
                # Update config to disable or remove WAF if active
                try:
                    dist_config_res = cf.get_distribution_config(Id=dist_id)
                    config = dist_config_res['DistributionConfig']
                    etag = dist_config_res['ETag']
                    
                    changed = False
                    if config.get('WebACLId') != '':
                        print(f"    Disassociating Web ACL from CloudFront {dist_id}...")
                        config['WebACLId'] = ''
                        changed = True
                    if config['Enabled']:
                        print(f"    Disabling CloudFront Distribution {dist_id}...")
                        config['Enabled'] = False
                        changed = True
                    if changed:
                        cf.update_distribution(DistributionConfig=config, Id=dist_id, IfMatch=etag)
                        print(f"    Successfully updated CloudFront configuration.")
                except Exception as e:
                    print(f"    Failed to update CloudFront Distribution {dist_id}: {e}")
    except Exception as e:
        if 'AccessDenied' not in str(e):
            print(f"  Error scanning CloudFront: {e}")
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
            print(f"  [{waf_region}] Found WAFv2 Web ACL: {name} (Scope: {scope})")
            found.append({'type': 'WAFv2 Web ACL', 'id': acl_id, 'name': name, 'region': waf_region, 'arn': arn, 'scope': scope})
            
            if not dry_run:
                try:
                    acl_details = waf.get_web_acl(Name=name, Id=acl_id, Scope=scope)
                    lock_token = acl_details['LockToken']
                    
                    # Delete regional associations
                    if scope == 'REGIONAL':
                        associations = waf.list_resources_for_web_acl(WebACLArn=arn).get('ResourceArns', [])
                        for res_arn in associations:
                            print(f"    Disassociating resource {res_arn} from WAF {name}...")
                            waf.disassociate_web_acl(ResourceArn=res_arn)
                            
                    print(f"    Deleting WAFv2 Web ACL: {name}...")
                    waf.delete_web_acl(Name=name, Id=acl_id, Scope=scope, LockToken=lock_token)
                    print(f"    Successfully deleted WAFv2 Web ACL: {name}")
                except Exception as e:
                    print(f"    Failed to delete WAFv2 Web ACL {name}: {e}")
    except Exception:
        pass
    return found

# S3 Buckets manager
def process_s3(session, dry_run=True):
    print("Scanning S3 Buckets...")
    found = []
    try:
        s3_client = session.client('s3', config=TIMEOUT_CONFIG)
        response = s3_client.list_buckets()
        buckets = response.get('Buckets', [])
        
        for bucket in buckets:
            name = bucket['Name']
            print(f"  Found Bucket: {name}")
            found.append({'type': 'S3 Bucket', 'id': name, 'region': 'global'})
            
            if not dry_run:
                print(f"    Deleting S3 Bucket: {name} (clearing contents first)...")
                try:
                    s3_resource = session.resource('s3', config=TIMEOUT_CONFIG)
                    bucket_obj = s3_resource.Bucket(name)
                    bucket_obj.object_versions.delete()
                    bucket_obj.objects.all().delete()
                    s3_client.delete_bucket(Bucket=name)
                    print(f"    Successfully deleted bucket: {name}")
                except Exception as e:
                    print(f"    Failed to delete bucket {name}: {e}")
    except Exception as e:
        if 'AccessDenied' not in str(e):
            print(f"  Failed to scan S3: {e}")
    return found

# Lightsail Manager
def process_lightsail(session, dry_run=True):
    print("Scanning Lightsail resources...")
    lightsail_regions = ['us-east-1', 'us-east-2', 'us-west-2', 'eu-west-1', 'eu-west-2', 'eu-central-1', 'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1', 'ap-northeast-2', 'ap-south-1', 'ca-central-1']
    found = []
    
    for r in lightsail_regions:
        try:
            ls = session.client('lightsail', region_name=r, config=TIMEOUT_CONFIG)
            
            # Instances
            instances = ls.get_instances().get('instances', [])
            for inst in instances:
                name = inst['name']
                print(f"  Found Lightsail Instance: {name} in {r}")
                found.append({'type': 'Lightsail Instance', 'id': name, 'region': r})
                if not dry_run:
                    print(f"    Deleting Lightsail Instance: {name}")
                    ls.delete_instance(instanceName=name)
            
            # Databases
            dbs = ls.get_relational_databases().get('relationalDatabases', [])
            for db in dbs:
                name = db['name']
                print(f"  Found Lightsail Database: {name} in {r}")
                found.append({'type': 'Lightsail Database', 'id': name, 'region': r})
                if not dry_run:
                    print(f"    Deleting Lightsail Database: {name}")
                    ls.delete_relational_database(relationalDatabaseName=name, skipFinalSnapshot=True)
        except Exception:
            pass
    return found

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
            print(f"  [{region}] Found EC2 Instance: {inst_id}")
            found.append({'type': 'EC2 Instance', 'id': inst_id, 'region': region})
            if not dry_run:
                print(f"    Terminating EC2 Instance: {inst_id}")
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
            print(f"  [{region}] Found EBS Volume: {vol_id} ({state})")
            found.append({'type': 'EBS Volume', 'id': vol_id, 'region': region})
            if not dry_run:
                if state == 'in-use':
                    try:
                        ec2.detach_volume(VolumeId=vol_id, Force=True)
                        time.sleep(2)
                    except Exception: pass
                print(f"    Deleting EBS Volume: {vol_id}")
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
            print(f"  [{region}] Found Elastic IP: {public_ip}")
            found.append({'type': 'Elastic IP', 'id': public_ip, 'region': region})
            if not dry_run:
                if association_id:
                    try: ec2.disassociate_address(AssociationId=association_id)
                    except Exception: pass
                if alloc_id:
                    print(f"    Releasing Elastic IP: {public_ip}")
                    ec2.release_address(AllocationId=alloc_id)
    except Exception: pass

    # 4. NAT Gateways
    try:
        nat_gws = ec2.describe_nat_gateways().get('NatGateways', [])
        for gw in nat_gws:
            if gw['State'] not in ['deleted', 'deleting']:
                gw_id = gw['NatGatewayId']
                print(f"  [{region}] Found NAT Gateway: {gw_id}")
                found.append({'type': 'NAT Gateway', 'id': gw_id, 'region': region})
                if not dry_run:
                    print(f"    Deleting NAT Gateway: {gw_id}")
                    ec2.delete_nat_gateway(NatGatewayId=gw_id)
    except Exception: pass

    # 5. VPC Endpoints
    try:
        endpoints = ec2.describe_vpc_endpoints().get('VpcEndpoints', [])
        for ep in endpoints:
            if ep['State'] != 'deleted':
                ep_id = ep['VpcEndpointId']
                print(f"  [{region}] Found VPC Endpoint: {ep_id}")
                found.append({'type': 'VPC Endpoint', 'id': ep_id, 'region': region})
                if not dry_run:
                    print(f"    Deleting VPC Endpoint: {ep_id}...")
                    ec2.delete_vpc_endpoints(VpcEndpointIds=[ep_id])
    except Exception: pass

    # 6. Load Balancers (ALB/NLB)
    try:
        elbv2 = session.client('elbv2', region_name=region, config=TIMEOUT_CONFIG)
        for lb in elbv2.describe_load_balancers().get('LoadBalancers', []):
            arn = lb['LoadBalancerArn']
            print(f"  [{region}] Found Load Balancer: {lb['LoadBalancerName']}")
            found.append({'type': 'Load Balancer (v2)', 'id': arn, 'region': region})
            if not dry_run:
                print(f"    Deleting Load Balancer: {lb['LoadBalancerName']}")
                elbv2.delete_load_balancer(LoadBalancerArn=arn)
    except Exception: pass

    # 7. RDS DB Instances
    try:
        for db in rds.describe_db_instances().get('DBInstances', []):
            db_id = db['DBInstanceIdentifier']
            print(f"  [{region}] Found RDS Instance: {db_id}")
            found.append({'type': 'RDS DB Instance', 'id': db_id, 'region': region})
            if not dry_run:
                if db.get('DeletionProtection', False):
                    try: rds.modify_db_instance(DBInstanceIdentifier=db_id, DeletionProtection=False, ApplyImmediately=True)
                    except Exception: pass
                print(f"    Deleting RDS DB Instance: {db_id}")
                rds.delete_db_instance(DBInstanceIdentifier=db_id, SkipFinalSnapshot=True)
    except Exception: pass

    # 8. RDS DB Cluster Snapshots
    try:
        for snap in rds.describe_db_cluster_snapshots().get('DBClusterSnapshots', []):
            if snap['SnapshotType'] == 'manual':
                snap_id = snap['DBClusterSnapshotIdentifier']
                print(f"  [{region}] Found RDS Cluster Snapshot: {snap_id}")
                found.append({'type': 'RDS Cluster Snapshot', 'id': snap_id, 'region': region})
                if not dry_run:
                    print(f"    Deleting RDS Cluster Snapshot: {snap_id}")
                    rds.delete_db_cluster_snapshot(DBClusterSnapshotIdentifier=snap_id)
    except Exception: pass

    # 9. RDS Automated Backups
    try:
        for backup in rds.describe_db_instance_automated_backups().get('DBInstanceAutomatedBackups', []):
            backup_arn = backup['DBInstanceAutomatedBackupsArn']
            print(f"  [{region}] Found RDS Retained Automated Backup for DB: {backup['DBInstanceIdentifier']}")
            found.append({'type': 'RDS Retained Backup', 'id': backup_arn, 'region': region})
            if not dry_run:
                print(f"    Deleting RDS Retained Backup...")
                rds.delete_db_instance_automated_backups(DbInstanceAutomatedBackupsArn=backup_arn)
    except Exception: pass

    # 10. DynamoDB Tables
    try:
        for table in ddb.list_tables().get('TableNames', []):
            print(f"  [{region}] Found DynamoDB Table: {table}")
            found.append({'type': 'DynamoDB Table', 'id': table, 'region': region})
            if not dry_run:
                print(f"    Deleting DynamoDB Table: {table}")
                ddb.delete_table(TableName=table)
    except Exception: pass

    return found

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
        print(f"[{index + 1}/{len(regions)}] Nuking region: {r}...")
        process_wafv2(session, r, 'REGIONAL', dry_run=False)
        process_regional(session, r, dry_run=False)

def main():
    print_header("AWS Terminator (Dry-Run Scan)")
    
    creds = get_credentials()
    session = get_session(creds)
    
    # Test authentication
    try:
        sts = session.client('sts', config=TIMEOUT_CONFIG)
        identity = sts.get_caller_identity()
        print(f"Successfully authenticated as:")
        print(f"  Account ID: {identity['Account']}")
        print(f"  User ARN: {identity['Arn']}")
    except Exception as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)
        
    print("\nRetrieving AWS regions...")
    regions = get_all_regions(session)
    print(f"Found {len(regions)} regions to scan.")
    
    # Run Dry-Run scan first
    all_resources = []
    
    print_header("Scanning Global Services")
    all_resources.extend(process_cloudfront(session, dry_run=True))
    all_resources.extend(process_wafv2(session, 'us-east-1', 'CLOUDFRONT', dry_run=True))
    all_resources.extend(process_s3(session, dry_run=True))
    all_resources.extend(process_lightsail(session, dry_run=True))
    
    print_header("Scanning Regional Services")
    for index, r in enumerate(regions):
        print(f"[{index + 1}/{len(regions)}] Scanning region: {r}...")
        res_waf = process_wafv2(session, r, 'REGIONAL', dry_run=True)
        all_resources.extend(res_waf)
        res_reg = process_regional(session, r, dry_run=True)
        all_resources.extend(res_reg)
        
    # Summary of findings
    print_header("Scan Summary")
    if not all_resources:
        print("No active billing resources found in this AWS account.")
        return
        
    total_savings = 0.0
    print(f"Total resources found: {len(all_resources)}")
    print("\nSummary List with Cost Estimates:")
    for item in all_resources:
        name_str = f" ({item['name']})" if 'name' in item else ""
        region_str = f" in region {item['region']}" if 'region' in item else " (global)"
        
        # Calculate cost estimates
        cost_baseline = PRICING_ESTIMATES.get(item['type'], 0.0)
        cost_str = f"${cost_baseline:.2f}/mo baseline" if cost_baseline > 0 else "usage-dependent / free"
        total_savings += cost_baseline
        
        print(f"  - {item['type']}: {item['id']}{name_str}{region_str} [{cost_str}]")
        
    print("-" * 60)
    print(f"ESTIMATED MONTHLY SAVINGS BY NUKING: ${total_savings:.2f} / month")
    print("=" * 60)
    
    # Interactive confirmation prompt
    try:
        confirm = input("\n⚠️  Are you absolutely sure you want to delete all the above resources? (Type 'yes' to nuke): ").strip().lower()
        if confirm == 'yes':
            run_nuke(session, regions, all_resources)
            print_header("Nuke Process Complete")
            print("NUKE PROCESS FINISHED. Some deletions are asynchronous and take time.")
            print("Please re-run the script to verify all resources are successfully deleted.")
            print("=" * 60)
        else:
            print("\nNuke cancelled. No resources were deleted.")
    except KeyboardInterrupt:
        print("\nNuke cancelled.")
        sys.exit(0)

if __name__ == '__main__':
    main()
