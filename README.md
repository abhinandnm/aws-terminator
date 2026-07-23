# AWS Eraser 🧹

The **fastest and simplest solution** to scan, audit, and clean active billing resources across all AWS regions. A single-file, zero-cloud-setup Python CLI utility to stop unexpected AWS billing charges instantly.

![AWS Eraser Banner](assets/banner.png?v=5)

## Release

**v1.1.0 – Interactive Selective Deletion & Advanced Resource Management**

- **Selective Manual Deletion:** Choose between nuking all resources or picking specific resources/ranges manually (`1, 3, 5-8`).
- **EC2 Termination & EBS Volume Wait:** Interactively prompts to wait for EC2 instance shutdown when attached EBS volumes are locked (`VolumeInUse`).
- **EBS Snapshots Support:** Scans and purges user-created EC2 EBS Snapshots.
- **Instant Re-Scan & Exit Loop:** Press `[ENTER]` at the end of a run to immediately re-scan and verify deletions, or press `[ESC]` / type `exit` to quit.
- **Smart Cost-Explorer Handling:** Distinguishes `DataUnavailableException` from real permission errors and proceeds automatically.

> [!WARNING]
> This tool is highly destructive and irreversible. Confirming the deletion prompt will permanently delete resources (including databases, EC2 instances, S3 buckets, and WAF configurations) from the target AWS account. Always review the scan results and billing details before typing 'yes'.

---

## Features

* **Flexible Deletion Options:** Choose to **Nuke ALL resources** at once or **Select specific resources manually** by number or range.
* **Interactive Confirmation:** Displays discovered resources with standard item numbers `[1]`, `[2]`, `[3]` and requires explicit confirmation before executing any deletion commands.
* **EBS Volume Wait Handler:** Automatically detects volumes attached to terminating instances and offers to poll and force-delete them once EC2 shutdown completes.
* **Instant Re-Scan Loop:** Re-run scans instantly with a single press of `[ENTER]` or exit cleanly with `[ESC]`.
* **ASCII CLI Design:** Colored, text-based CLI status logs with real-time loading spinners compatible across all command prompts and terminals.
* **Unbuffered Execution:** Real-time log streaming for continuous monitoring of deletion progress.
* **Intelligent Timeout Handling:** Configured with low connection timeouts to skip disabled or opt-in regions without hanging.
* **Secure Credential Entry:** Safely prompts for AWS access keys in the terminal if no local credentials file is found, keeping keys off disk.
* **Multi-Region Coverage:** Dynamically discovers and scans all active and opted-in AWS regions globally.

---

## Supported Resources

| Category | Resources Cleaned |
| :--- | :--- |
| **Compute** | EC2 Instances, Lightsail Instances, Lightsail Databases |
| **Storage** | S3 Buckets (clears all versions/objects first), EBS Volumes, **EBS Snapshots**, RDS Databases, RDS Snapshots, RDS Automated Backups |
| **Networking** | Elastic IPs, NAT Gateways, Load Balancers (ALB/NLB/CLB), VPC Endpoints |
| **Security** | WAFv2 Web ACLs (Global & Regional), CloudFront Associations |
| **Database** | DynamoDB Tables |

---

## Resources Not Cleaned (Limitations)

To prevent accidental lockouts and because of API limitations, this script does **not** delete:
* **IAM Users, Groups, Roles, & Policies:** (To avoid revoking the credentials currently running the script).
* **AWS Marketplace Subscriptions & Savings Plans:** (These are financial contracts and must be cancelled manually).
* **KMS Keys:** (Custom encryption keys require a minimum 7-day wait period before deletion).
* **Container Services:** ECS clusters, EKS Kubernetes configurations, and ECR container image registries.
* **Serverless Functions:** AWS Lambda and API Gateway deployments (though they generate no costs unless receiving traffic).
* **CloudWatch Log Groups:** (Historic system logs are preserved).

---

## Common Use Cases & Search Solutions

If you are searching Google for answers to these common AWS billing and administration problems, **AWS Eraser** provides the **fastest 1-click solution**:
* **What is the fastest way to delete all resources in an AWS account?** AWS Eraser scans all regions in seconds and wipes costly resources without deploying complex CloudFormation templates.
* **How to stop unexpected AWS billing charges immediately?** The script automatically finds running instances, unattached EBS volumes, EBS snapshots, NAT gateways, and databases quietly draining your account.
* **Can I select specific AWS resources to delete manually?** Yes! AWS Eraser presents a numbered summary list allowing you to pick specific items (`1, 3, 5-8`) or nuke everything.
* **Fastest way to nuke AWS account using Python?** Single-file `boto3` CLI script with zero dependencies beyond the AWS SDK.
* **AWS Cost Explorer shows unexpected fees, how to clean up fast?** Displays accrued monthly bill and lets you confirm deletion across all regions instantly.

---

## Getting Started

### 1. Installation

Download the stable release or clone this repository and install the required dependencies:

```bash
git clone https://github.com/abhinandnm/aws-eraser.git
cd aws-eraser
pip install -r requirements.txt
```

> **For Windows Users:** You can simply run the provided `run.bat` file (by double-clicking it or running `.\run.bat` in the terminal) to automatically install dependencies and launch the utility.

### 2. Usage

Execute the script directly in your terminal:
```bash
python aws_eraser.py
```

### 3. Execution Flow
1. The script checks for a local `credentials.json` file. If not found, it prompts the user to enter their AWS Access Key ID and Secret Access Key.
2. It fetches and displays the current monthly accrued bill grouped by service.
3. It scans all global regions and outputs a numbered list `[1]`, `[2]`, `[3]` of active billing resources.
4. It prompts for deletion choice:
   - **Option 1: Nuke ALL resources**
   - **Option 2: Select specific resources to delete manually** (`1, 3, 5-8`)
   - **Option 3: Cancel and exit**
5. Executes targeted deletion calls with live loading spinners.
6. Displays the re-scan prompt: **Press `[ENTER]` to re-run scan | Type 'exit' (or press `[ESC]`) to quit**.

#### 4. Active Resource Termination Output
![AWS Eraser Nuke Deletion Execution Preview](assets/deletion_preview.png?v=5)

---

## Troubleshooting Cost Explorer Access

If the script shows an `Access Denied or Cost Explorer disabled` warning even after attaching the IAM policy, follow these two steps to activate billing access:

1. **Activate IAM Billing Access (Must be done by the AWS Root Account):**
   * Sign in to the AWS Console as the **Root User** (using the primary email address of the account, not an IAM user).
   * Open the [AWS Account Settings Page](https://console.aws.amazon.com/billing/home?#/account).
   * Scroll down to the **IAM User and Role Access to Billing Information** section and click **Edit**.
   * Check the box for **Activate IAM Access** and click **Update**.

2. **Attach the IAM Policy:**
   * Open the [IAM Users Console](https://console.aws.amazon.com/iam/home?#/users).
   * Select your target IAM user/role, click **Add Permissions**, and search for the AWS managed policy **`AWSBillingReadOnlyAccess`**.
   * Attach it to the user.

> **Note:** When the script detects a `DataUnavailableException`, it will display an informational message that Cost Explorer is still initializing and will automatically continue scanning resources without aborting. No policy changes are required in that case; just wait up to 24 hours for billing data to become available.

---

## Contributing

Contributions are welcome. Please open an issue or submit a pull request if you want to add support for more AWS resource types.

## License

This project is licensed under the MIT License.
