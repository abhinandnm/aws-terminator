# AWS Eraser - IAM Permissions Guide

If you encounter insufficient permission warnings while running `aws_eraser.py`, it means your current IAM User or Role lacks the API authorizations required to scan or delete resources under certain services.

To resolve these warnings, sign in to the **AWS IAM Console**, select your User or Role, click **Add Permissions**, and attach the corresponding pre-made AWS managed policies below.

---

## Recommended Managed Policies

| Service | Insufficient Permission Error | AWS Managed Policy Name to Attach |
| :--- | :--- | :--- |
| **All Services** | Any scanning/deletion errors | **`AdministratorAccess`** *(Recommended for full cleanup)* |
| **Cost Explorer** | Access Denied / Cost Explorer disabled | **`AWSBillingReadOnlyAccess`** |
| **CloudFront** | CloudFront skipped | **`CloudFrontFullAccess`** |
| **DynamoDB** | DynamoDB skipped | **`AmazonDynamoDBFullAccess`** |
| **Lightsail** | Lightsail skipped | **`AmazonLightsailFullAccess`** |
| **RDS** | RDS skipped | **`AmazonRDSFullAccess`** |
| **S3** | S3 skipped | **`AmazonS3FullAccess`** |
| **WAFv2** | WAFv2 skipped | **`AWSWAFFullAccess`** |

---

## How to attach policies in the AWS Console

1. Open the [AWS IAM Console](https://console.aws.amazon.com/iam/home?#/users).
2. Click on the **User** or **Role** that corresponds to the AWS credentials you configured.
3. Under the **Permissions** tab, click **Add permissions** -> **Attach policies**.
4. Search for the policy name from the table above (e.g. `AmazonS3FullAccess`).
5. Select the checkbox next to the policy and click **Add permissions** at the bottom.
