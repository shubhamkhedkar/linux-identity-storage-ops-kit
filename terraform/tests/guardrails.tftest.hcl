mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_ssm_parameter" {
    defaults = { value = "ami-0123456789abcdef0" }
  }
  mock_data "aws_subnet" {
    defaults = { availability_zone = "ap-south-1a" }
  }
  mock_resource "aws_kms_key" {
    defaults = { arn = "arn:aws:kms:ap-south-1:123456789012:key/00000000-0000-0000-0000-000000000000" }
  }
}

variables {
  vpc_id       = "vpc-0123456789abcdef0"
  subnet_id    = "subnet-0123456789abcdef0"
  egress_cidrs = ["10.0.0.0/16"]
}

run "imdsv2_and_encryption" {
  command = plan

  assert {
    condition     = aws_instance.host.metadata_options[0].http_tokens == "required"
    error_message = "IMDSv2 must be enforced."
  }
  assert {
    condition     = aws_instance.host.root_block_device[0].encrypted
    error_message = "Root volume must be encrypted."
  }
  assert {
    condition     = aws_ebs_volume.data.encrypted && aws_ebs_volume.data.size == 5
    error_message = "Data volume must be encrypted and 5 GiB by default."
  }
  assert {
    condition     = aws_kms_key.ebs.enable_key_rotation
    error_message = "KMS key rotation must be on."
  }
}

run "ssm_access_and_https_only_egress" {
  command = plan

  assert {
    condition     = aws_iam_role_policy_attachment.ssm.policy_arn == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    error_message = "Access must be through SSM Session Manager."
  }
  assert {
    condition     = alltrue([for e in aws_security_group.host.egress : e.from_port == 443 && e.to_port == 443])
    error_message = "Egress is limited to HTTPS."
  }
}

run "volume_same_az_as_subnet" {
  command = plan

  assert {
    condition     = aws_ebs_volume.data.availability_zone == "ap-south-1a"
    error_message = "EBS volume must be in the instance subnet AZ."
  }
}

run "rejects_bad_egress" {
  command = plan

  variables {
    egress_cidrs = ["not-a-cidr"]
  }

  expect_failures = [var.egress_cidrs]
}

run "rejects_oversized_volume" {
  command = plan

  variables {
    data_volume_size_gib = 5000
  }

  expect_failures = [var.data_volume_size_gib]
}
