# ---------------------------------------------------------------------------
# Tự sinh toàn bộ secret, tạo K8s Secret `greenmart-secrets`, rồi chạy Job tạo 5 database + 5 user trên RDS.
# (RDS nằm trong subnet private nên Terraform không kết nối trực tiếp từ máy local được;
#  Job chạy trong cluster, cùng VPC, nên vào được.)
# ---------------------------------------------------------------------------

locals {
  databases = {
    user      = { db = "user_db", user = "user_svc", env = "USER_DB_PASSWORD" }
    catalog   = { db = "catalog_db", user = "catalog_svc", env = "CATALOG_DB_PASSWORD" }
    order     = { db = "order_db", user = "order_svc", env = "ORDER_DB_PASSWORD" }
    promotion = { db = "promotion_db", user = "promotion_svc", env = "PROMOTION_DB_PASSWORD" }
    web       = { db = "web_db", user = "web_svc", env = "WEB_DB_PASSWORD" }
  }
}

# special = false: tránh ký tự làm hỏng SQL / shell.
resource "random_password" "db" {
  for_each = local.databases
  length   = 32
  special  = false
}

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "internal_api_token" {
  length  = 48
  special = false
}

# Mật khẩu master do RDS tự sinh, lưu ở Secrets Manager (JSON: username, password).
data "aws_secretsmanager_secret_version" "rds_master" {
  secret_id = aws_db_instance.mysql.master_user_secret[0].secret_arn
}

locals {
  rds_master_password = jsondecode(data.aws_secretsmanager_secret_version.rds_master.secret_string)["password"]
}

resource "kubernetes_namespace_v1" "app" {
  metadata {
    name = var.k8s_namespace
    labels = {
      "app.kubernetes.io/part-of" = "greenmart"
    }
  }

  # kubectl apply -k sẽ thêm nhãn/annotation khác; không coi là drift.
  lifecycle {
    ignore_changes = [metadata[0].labels, metadata[0].annotations]
  }
}

resource "kubernetes_secret_v1" "app" {
  metadata {
    name      = "greenmart-secrets"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      "app.kubernetes.io/name"    = "secrets"
      "app.kubernetes.io/part-of" = "greenmart"
    }
  }

  type = "Opaque"

  data = merge(
    {
      SECRET_KEY          = random_password.secret_key.result
      INTERNAL_API_TOKEN  = random_password.internal_api_token.result
      EMAIL_HOST_PASSWORD = var.email_host_password
      RDS_ADMIN_USER      = var.db_master_username
      RDS_ADMIN_PASSWORD  = local.rds_master_password
      MYSQL_ROOT_PASSWORD = local.rds_master_password # data-migrator dùng key này
    },
    { for k, v in local.databases : v.env => random_password.db[k].result }
  )
}

# Tạo 5 database + 5 tài khoản (idempotent, đặt lại mật khẩu theo Secret). Chạy trong cluster, xong mới tiếp tục.
resource "kubernetes_job_v1" "rds_init" {
  metadata {
    name      = "rds-init"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      "app.kubernetes.io/name"    = "rds-init"
      "app.kubernetes.io/part-of" = "greenmart"
    }
  }

  spec {
    backoff_limit = 6

    template {
      metadata {
        labels = { "app.kubernetes.io/name" = "rds-init" }
      }

      spec {
        automount_service_account_token = false
        restart_policy                  = "OnFailure"

        container {
          name  = "mysql"
          image = "mysql:8.0"

          env {
            name  = "DB_HOST"
            value = aws_db_instance.mysql.address
          }
          env {
            name = "RDS_ADMIN_USER"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.app.metadata[0].name
                key  = "RDS_ADMIN_USER"
              }
            }
          }
          env {
            name = "MYSQL_PWD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.app.metadata[0].name
                key  = "RDS_ADMIN_PASSWORD"
              }
            }
          }

          dynamic "env" {
            for_each = local.databases
            content {
              name = env.value.env
              value_from {
                secret_key_ref {
                  name = kubernetes_secret_v1.app.metadata[0].name
                  key  = env.value.env
                }
              }
            }
          }

          command = ["sh", "-ec", <<-EOT
            mysql -h "$DB_HOST" -P 3306 -u "$RDS_ADMIN_USER" <<SQL
            %{for k, v in local.databases~}
            CREATE DATABASE IF NOT EXISTS ${v.db} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            CREATE USER IF NOT EXISTS '${v.user}'@'%' IDENTIFIED WITH mysql_native_password BY '${"$"}${v.env}';
            ALTER USER '${v.user}'@'%' IDENTIFIED BY '${"$"}${v.env}';
            GRANT ALL PRIVILEGES ON ${v.db}.* TO '${v.user}'@'%';
            %{endfor~}
            FLUSH PRIVILEGES;
            SQL
          EOT
          ]
        }
      }
    }
  }

  wait_for_completion = true

  timeouts {
    create = "10m"
    update = "10m"
  }

  depends_on = [
  aws_vpc_security_group_ingress_rule.rds_from_cluster,
  aws_vpc_security_group_ingress_rule.rds_from_vpc,
  ]
}
