# AWS Terminator (Python) 🚀

A lightweight, unbuffered, and highly optimized Python script designed to scan and destroy active billing resources across all AWS regions to prevent unexpected cloud bills.

> [!WARNING]
> **This tool is highly destructive and irreversible.** 
> Running this script with the `--nuke` flag will permanently delete resources (like databases, EC2 instances, S3 buckets, and WAF configurations) from your AWS account. Always review the scan results in dry-run mode before proceeding.

---

## Key Features

* **Unbuffered Execution:** Prints logs in real-time so you can monitor progress.
* **Instant Skipping:** Configured with a 2-second connection timeout to instantly skip disabled or opt-in regions, preventing long connection hangs.
* **Interactive Console Entry:** Prompts for credentials directly in the terminal if no config file is found (eliminating the need to store keys on disk).
* **Comprehensive Multi-Region Coverage:** Automatically scans all 34 active AWS regions.

---

## Supported Resources

| Category | Resources Cleaned |
| :--- | :--- |
| **Compute** | EC2 Instances, Lightsail Instances, Lightsail Databases |
| **Storage** | S3 Buckets (clears all versions/objects first), EBS Volumes, RDS Databases, RDS Snapshots, RDS Automated Backups |
| **Networking** | Elastic IPs, NAT Gateways, Load Balancers (ALB/NLB/CLB), VPC Endpoints, VPN Connections, VPN Gateways, Customer Gateways, Transit Gateways |
| **Security** | WAFv2 Web ACLs (Global & Regional), CloudFront Associations |
| **Database** | DynamoDB Tables |

---

## Getting Started

### 1. Installation

Clone this repository and install the official AWS SDK (`boto3`):

```bash
git clone https://github.com/YOUR_USERNAME/aws-terminator.git
cd aws-terminator
pip install boto3
```

### 2. Usage

Run the script. It supports two modes:

#### A. Scan Only (Dry-Run Mode) - Safe
This will scan all regions and list active resources without deleting anything:
```bash
python aws_terminator.py
```

#### B. Nuke Mode (Destructive Deletion) - Dangerous
This will scan all regions and delete any found billing resources:
```bash
python aws_terminator.py --nuke
```

### 3. Authentication Options

When you run the script, it will check for credentials in this order:
1. A local `credentials.json` file in the folder (format: `{"aws_access_key_id": "...", "aws_secret_access_key": "..."}`).
2. Standard environment variables (`AWS_ACCESS_KEY_ID`, etc.).
3. **Console Prompt (Default):** If neither is found, it will securely prompt you to type or paste your keys directly into the terminal console.

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request if you want to add support for more AWS resource types (e.g., ECS, EKS, SageMaker, etc.).

## License

This project is licensed under the [MIT License](LICENSE).
