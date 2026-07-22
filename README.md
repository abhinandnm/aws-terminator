# AWS Terminator (Python) 🚀

A lightweight, unbuffered, and highly optimized Python script designed to scan active billing resources across all AWS regions, estimate your monthly cost savings, and safely prompt you for confirmation before nuking everything.

> [!WARNING]
> **This tool is highly destructive and irreversible.** 
> Confirming the nuke prompt will permanently delete resources (like databases, EC2 instances, S3 buckets, and WAF configurations) from your AWS account. Always review the scan results and cost estimates before typing 'yes'.

---

## Key Features

* **Interactive Confirmation:** Always scans in dry-run mode first, shows you the resources and monthly pricing baseline, and asks: `Are you absolutely sure you want to delete all the above resources? (Type 'yes' to nuke)`.
* **Cost Estimation:** Estimates the monthly billing costs for detected resources (like NAT Gateways, Elastic IPs, EC2, RDS, and WAF) so you know exactly where your bills are coming from.
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

Run the script:
```bash
python aws_terminator.py
```

### 3. Execution Flow
1. The script will look for `credentials.json` in the folder. If not found, it will securely prompt you to type or paste your AWS Access Key ID and Secret Access Key.
2. It will query all 34 regions and list all active billing resources.
3. It will display the **Estimated Monthly Savings** by nuking these resources.
4. It will prompt you: `Are you absolutely sure you want to delete all the above resources? (Type 'yes' to nuke)`.
5. If you type `yes`, it will run the deletion pass and wipe the resources.

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request if you want to add support for more AWS resource types (e.g., ECS, EKS, SageMaker, etc.).

## License

This project is licensed under the [MIT License](LICENSE).
