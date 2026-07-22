# Contributing to AWS Eraser 🤝

First off, thank you for considering contributing to AWS Eraser! It is people like you who make open source such a wonderful place to build tools.

## How Can You Contribute?

### 1. Adding Support for New AWS Resources
Adding support for new resource types is easy:
1. Open `aws_eraser.py`.
2. Locate the `PRICING_ESTIMATES` dictionary and add an approximate monthly cost baseline for the new resource (if applicable).
3. If it's a regional service, add the boto3 client call and scanning/deletion logic inside the `process_regional` function.
4. If it's a global service, add a dedicated helper function (like `process_s3` or `process_cloudfront`) and call it in `main()` and `run_nuke()`.
5. Test your changes in dry-run mode to ensure no accidental deletions occur!

## Pull Request Guidelines
* Keep pull requests small and focused on a single feature or bug fix.
* Make sure your code is formatted and syntactically valid.
* Update `README.md` if you added support for new resource types.
