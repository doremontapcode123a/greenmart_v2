# ---------------------------------------------------------------------------
# Giám sát phía AWS, để Grafana đặt cạnh Prometheus và so sánh độ lệch:
#   - Addon amazon-cloudwatch-observability: CloudWatch Container Insights (CPU/RAM pod, node) + log container
#   - Role IRSA cho Grafana (đọc CloudWatch + X-Ray) và X-Ray daemon (ghi trace)
#   - Luật lấy mẫu X-Ray: bỏ health/metrics, ghi trace request thật theo var.xray_sample_rate
# Phụ thuộc OIDC provider của cluster (đã dùng ở ebs.tf).
# ---------------------------------------------------------------------------

locals {
  irsa_roles = var.enable_monitoring ? {
    cloudwatch-agent = {
      namespace = "amazon-cloudwatch"
      sa        = "cloudwatch-agent"
      policies  = ["arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy", "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"]
    }
    grafana = {
      namespace = "monitoring"
      sa        = "grafana"
      policies  = ["arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess", "arn:aws:iam::aws:policy/AWSXrayReadOnlyAccess"]
    }
    xray-daemon = {
      namespace = "monitoring"
      sa        = "xray-daemon"
      policies  = ["arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"]
    }
  } : {}

  irsa_policy_attachments = merge([
    for role, cfg in local.irsa_roles : {
      for idx, arn in cfg.policies : "${role}-${idx}" => { role = role, policy_arn = arn }
    }
  ]...)
}

data "aws_iam_policy_document" "irsa_assume" {
  for_each = local.irsa_roles

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["system:serviceaccount:${each.value.namespace}:${each.value.sa}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "irsa" {
  for_each           = local.irsa_roles
  name               = "${var.name}-${var.cluster_name}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume[each.key].json
}

resource "aws_iam_role_policy_attachment" "irsa" {
  for_each   = local.irsa_policy_attachments
  role       = aws_iam_role.irsa[each.value.role].name
  policy_arn = each.value.policy_arn
}

# CloudWatch Container Insights (metric theo pod/node vào namespace ContainerInsights).
# Lưu ý chi phí: addon cũng đẩy log container lên CloudWatch Logs (tính theo dung lượng ingest).
resource "aws_eks_addon" "cloudwatch_observability" {
  count                       = var.enable_monitoring ? 1 : 0
  cluster_name                = var.cluster_name
  addon_name                  = "amazon-cloudwatch-observability"
  service_account_role_arn    = aws_iam_role.irsa["cloudwatch-agent"].arn
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  configuration_values = jsonencode({
    manager = {
      applicationSignals = {
        autoMonitor = {
          monitorAllServices = false
        }
      }
    }
   })
  depends_on = [aws_iam_role_policy_attachment.irsa]
}
  
# Luật lấy mẫu X-Ray (số nhỏ = ưu tiên cao). Không ghi trace cho health check của kubelet/ALB và /metrics của Prometheus.
resource "aws_xray_sampling_rule" "skip_health" {
  count          = var.enable_monitoring ? 1 : 0
  rule_name      = "greenmart-skip-health"
  priority       = 100
  version        = 1
  reservoir_size = 0
  fixed_rate     = 0
  url_path       = "/health*"
  host           = "*"
  http_method    = "*"
  service_name   = "greenmart-*"
  service_type   = "*"
  resource_arn   = "*"
}

resource "aws_xray_sampling_rule" "skip_metrics" {
  count          = var.enable_monitoring ? 1 : 0
  rule_name      = "greenmart-skip-metrics"
  priority       = 101
  version        = 1
  reservoir_size = 0
  fixed_rate     = 0
  url_path       = "/metrics*"
  host           = "*"
  http_method    = "*"
  service_name   = "greenmart-*"
  service_type   = "*"
  resource_arn   = "*"
}

resource "aws_xray_sampling_rule" "greenmart_all" {
  count          = var.enable_monitoring ? 1 : 0
  rule_name      = "greenmart-all"
  priority       = 1000
  version        = 1
  reservoir_size = 1
  fixed_rate     = var.xray_sample_rate
  url_path       = "*"
  host           = "*"
  http_method    = "*"
  service_name   = "greenmart-*"
  service_type   = "*"
  resource_arn   = "*"
}
