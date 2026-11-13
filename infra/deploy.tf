# CI updates the server after each merge to main (.github/workflows/images.yml, job
# "deploy"). GitHub signs in to AWS with OIDC, so the repo holds no AWS keys, and the
# role may only run the `data-platform-update` document below on this one instance:
# it can update the server, not run arbitrary commands on it. Disable with
# `github_repo = null`.

locals {
  deploy = var.github_repo != null
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = local.deploy && var.github_oidc_provider_arn == null ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  github_oidc_provider_arn = local.deploy ? coalesce(var.github_oidc_provider_arn, one(aws_iam_openid_connect_provider.github[*].arn)) : null
}

# Runs on the instance as root (SSM Agent); the update itself runs as `ubuntu`, which
# owns the checkout and can run Docker. `commit` must be a full SHA, so nothing else
# reaches the shell. It runs deploy.py from that commit, so a new deploy script works
# on its first deploy. flock: a second deploy waits for the first instead of racing it.
resource "aws_ssm_document" "update" {
  count           = local.deploy ? 1 : 0
  name            = "data-platform-update-${var.env}"
  document_type   = "Command"
  document_format = "JSON"
  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Update data-platform to a commit on main (infra/server/deploy.py)."
    parameters = {
      commit = {
        type           = "String"
        description    = "Full commit SHA on main."
        allowedPattern = "^[0-9a-f]{40}$"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "update"
      inputs = {
        timeoutSeconds = "4200" # deploy.py waits up to 60 minutes for a Dagster run
        runCommand = [
          "set -eu",
          "exec flock -w 4200 /run/data-platform-update.lock sudo -iu ubuntu bash -euo pipefail -c 'cd ${var.repo_dir} && git fetch --quiet origin main && git show {{ commit }}:infra/server/deploy.py | python3 - {{ commit }}'",
        ]
      }
    }]
  })
}

resource "aws_iam_role" "deploy" {
  count = local.deploy ? 1 : 0
  name  = "data-platform-${var.env}-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.github_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          # Only workflows running on main of this repo, never PRs or forks.
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "deploy" {
  count = local.deploy ? 1 : 0
  name  = "run-update-document"
  role  = aws_iam_role.deploy[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ssm:SendCommand"
        Resource = [aws_instance.this.arn, aws_ssm_document.update[0].arn]
      },
      {
        # Reading a command's status and output; neither action supports resource scoping.
        Effect   = "Allow"
        Action   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
        Resource = "*"
      },
    ]
  })
}
