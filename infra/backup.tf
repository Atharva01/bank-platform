# Daily automated EBS snapshot of the root volume via AWS Data Lifecycle
# Manager - the one thing genuinely absent from the original bare-VPS
# plan (no backup story at all). Docker's named volumes (postgres_data,
# traefik-public-certificates) live on this volume under /var/lib/docker,
# so this snapshot covers whole-instance disaster recovery, including the
# DB's on-disk files. Postgres-level pg_dump-to-S3 backups would be a
# further improvement but are out of scope here.

data "aws_iam_policy_document" "dlm_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["dlm.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dlm" {
  name               = "bank-platform-dlm"
  assume_role_policy = data.aws_iam_policy_document.dlm_assume_role.json
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "app_backup" {
  description        = "bank-platform daily EBS snapshot of the app instance root volume"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    target_tags = {
      Backup = "bank-platform"
    }

    schedule {
      name = "daily"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["05:00"]
      }

      retain_rule {
        count = 7
      }

      tags_to_add = {
        SnapshotCreator = "dlm-bank-platform"
      }
    }
  }
}
