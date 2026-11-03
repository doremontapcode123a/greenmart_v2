# ---------------------------------------------------------------------------
# EBS cho ảnh sản phẩm.
# Volume được CSI driver tạo động khi PVC `greenmart-media` (StorageClass `ebs-gp3`, k8s/overlays/eks) được dùng.
# Terraform lo phần hạ tầng đi kèm:
#   1) IAM role (IRSA) + addon aws-ebs-csi-driver để cluster tạo/gắn được EBS
#   2) Chính sách snapshot hằng ngày (DLM) cho volume có tag greenmart-backup=true
# ---------------------------------------------------------------------------

data "aws_iam_openid_connect_provider" "eks" {
  url = data.aws_eks_cluster.this.identity[0].oidc[0].issuer
}

locals {
  oidc_host = replace(data.aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")
}

# ----- EBS CSI driver -----
data "aws_iam_policy_document" "ebs_csi_assume" {
  count = var.install_ebs_csi_addon ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["system:serviceaccount:kube-system:ebs-csi-controller-sa"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi" {
  count              = var.install_ebs_csi_addon ? 1 : 0
  name               = "${var.name}-${var.cluster_name}-ebs-csi"
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_assume[0].json
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  count      = var.install_ebs_csi_addon ? 1 : 0
  role       = aws_iam_role.ebs_csi[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_eks_addon" "ebs_csi" {
  count                       = var.install_ebs_csi_addon ? 1 : 0
  cluster_name                = var.cluster_name
  addon_name                  = "aws-ebs-csi-driver"
  service_account_role_arn    = aws_iam_role.ebs_csi[0].arn
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  depends_on = [aws_iam_role_policy_attachment.ebs_csi]
}

# ----- Snapshot hằng ngày cho volume gắn tag greenmart-backup=true (StorageClass ebs-gp3 tự gắn tag này) -----
data "aws_iam_policy_document" "dlm_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["dlm.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dlm" {
  name               = "${var.name}-${var.cluster_name}-dlm"
  assume_role_policy = data.aws_iam_policy_document.dlm_assume.json
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "ebs_daily" {
  description        = "Snapshot EBS hang ngay cho volume GreenMart"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    target_tags = {
      "greenmart-backup" = "true"
    }

    schedule {
      name = "daily"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["17:00"] # UTC = 00:00 giờ Việt Nam
      }

      retain_rule {
        count = var.ebs_snapshot_retention
      }

      copy_tags = true
    }
  }
}
