# AWS Terminator - IAM Permissions Guide

If you encounter insufficient permission warnings while running `aws-terminator`, it means your current IAM User or Role lacks the API authorizations required to scan or delete resources under certain services.

To resolve these errors, you can either attach the AWS-managed policy **`AdministratorAccess`** to your IAM User/Role (recommended for complete cleanup), or attach a custom policy with the specific permission actions detailed below.

---

## 1. AWS Billing / Cost Explorer
If the script fails to retrieve the monthly accrued billing dashboard, ensure your IAM role includes the following actions, and that **IAM Billing Access** is enabled in your AWS Root Account:

* **AWS Console Page:** [AWS Billing Settings](https://console.aws.amazon.com/billing/home?#/account)
* **Required Actions:**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "ce:GetCostAndUsage"
        ],
        "Resource": "*"
      }
    ]
  }
  ```
* **AWS Managed Policy Alternative:** Attach the **`AWSBillingReadOnlyAccess`** policy.

---

## 2. CloudFront (Content Delivery Network)
Lacking permissions for CloudFront skips scanning and deleting distribution networks.

* **Required Actions:**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "cloudfront:ListDistributions",
          "cloudfront:GetDistribution",
          "cloudfront:GetDistributionConfig",
          "cloudfront:UpdateDistribution",
          "cloudfront:DeleteDistribution"
        ],
        "Resource": "*"
      }
    ]
  }
  ```

---

## 3. DynamoDB (NoSQL Database Service)
Lacking permissions for DynamoDB skips list and delete routines for tables.

* **Required Actions:**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "dynamodb:ListTables",
          "dynamodb:DescribeTable",
          "dynamodb:DeleteTable"
        ],
        "Resource": "*"
      }
    ]
  }
  ```

---

## 4. Lightsail (Virtual Private Servers)
Lacking permissions for Lightsail skips scanning or terminating VPS instances and relational databases.

* **Required Actions:**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "lightsail:GetInstances",
          "lightsail:DeleteInstance",
          "lightsail:GetRelationalDatabases",
          "lightsail:DeleteRelationalDatabase"
        ],
        "Resource": "*"
      }
    ]
  }
  ```

---

## 5. RDS (Relational Database Service)
Lacking permissions for RDS skips listing and deleting DB instances, automated backups, and cluster snapshots.

* **Required Actions:**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "rds:DescribeDBInstances",
          "rds:ModifyDBInstance",
          "rds:DeleteDBInstance",
          "rds:DescribeDBClusterSnapshots",
          "rds:DeleteDBClusterSnapshot",
          "rds:DescribeDBInstanceAutomatedBackups",
          "rds:DeleteDBInstanceAutomatedBackups"
        ],
        "Resource": "*"
      }
    ]
  }
  ```

---

## 6. S3 (Simple Storage Service)
Lacking permissions for S3 skips empty bucket operations, clearing object versions, and deleting buckets.

* **Required Actions:**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "s3:ListAllMyBuckets",
          "s3:ListBucket",
          "s3:ListBucketVersions",
          "s3:DeleteObject",
          "s3:DeleteObjectVersion",
          "s3:DeleteBucket"
        ],
        "Resource": "*"
      }
    ]
  }
  ```

---

## 7. WAFv2 (Web Application Firewall)
Lacking permissions for WAFv2 skips scanning, disassociating resources (like ALBs/CloudFront), or deleting Web ACLs.

* **Required Actions:**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "wafv2:ListWebACLs",
          "wafv2:GetWebACL",
          "wafv2:DeleteWebACL",
          "wafv2:ListResourcesForWebACL",
          "wafv2:DisassociateWebACL"
        ],
        "Resource": "*"
      }
    ]
  }
  ```
