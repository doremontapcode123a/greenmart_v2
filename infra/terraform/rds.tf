# ---------------------------------------------------------------------------
# RDS MySQL 8.0 cho 5 database của dự án (user_db, catalog_db, order_db, promotion_db, web_db).
# Các database và tài khoản theo service được tạo bởi Job `rds-init` trong k8s/overlays/eks.
# ---------------------------------------------------------------------------

data "aws_eks_cluster" "this" {
  name = var.cluster_name
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }

  tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }
}

locals {
  vpc_id        = data.aws_eks_cluster.this.vpc_config[0].vpc_id
  cluster_sg_id = data.aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  db_subnet_ids = length(var.db_subnet_ids) > 0 ? var.db_subnet_ids : data.aws_subnets.private.ids
}

resource "aws_db_subnet_group" "mysql" {
  name       = "${var.name}-mysql"
  subnet_ids = local.db_subnet_ids

  lifecycle {
    precondition {
      condition     = length(local.db_subnet_ids) >= 2
      error_message = "RDS cần ít nhất 2 subnet ở 2 AZ khác nhau. Truyền db_subnet_ids hoặc gắn tag kubernetes.io/role/internal-elb=1 cho subnet private."
    }
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.name}-rds-"
  description = "MySQL cho GreenMart - chi cho phep tu cluster EKS"
  vpc_id      = local.vpc_id

  lifecycle {
    create_before_destroy = true
  }
}

# Chỉ pod/node của cluster (security group của cluster) được kết nối cổng 3306.
resource "aws_vpc_security_group_ingress_rule" "rds_from_cluster" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = local.cluster_sg_id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL tu EKS cluster"
}

data "aws_vpc" "this" {
  id = local.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_vpc" {
  security_group_id = aws_security_group.rds.id
  cidr_ipv4         = data.aws_vpc.this.cidr_block
  ip_protocol       = "tcp"
  from_port         = 3306
  to_port           = 3306
  description       = "MySQL tu VPC (pod/node EKS)"
}

resource "aws_db_parameter_group" "mysql" {
  name_prefix = "${var.name}-mysql8-"
  family      = "mysql8.0"
  description = "utf8mb4 cho tieng Viet"

  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }

  parameter {
    name  = "collation_server"
    value = "utf8mb4_unicode_ci"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "mysql" {
  identifier     = "${var.name}-mysql"
  engine         = "mysql"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage > 0 ? var.db_max_allocated_storage : null
  storage_type          = "gp3"
  storage_encrypted     = true

  username = var.db_master_username
  # RDS tự sinh mật khẩu master và lưu trong AWS Secrets Manager (không nằm trong code/state dạng plaintext).
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.mysql.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.mysql.name
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period = var.db_backup_retention_days
  backup_window           = "17:00-18:00" # UTC = 00:00-01:00 giờ Việt Nam
  maintenance_window      = "sun:18:00-sun:19:00"
  copy_tags_to_snapshot   = true

  auto_minor_version_upgrade = true
  deletion_protection        = var.db_deletion_protection
  skip_final_snapshot        = var.db_skip_final_snapshot
  final_snapshot_identifier  = var.db_skip_final_snapshot ? null : "${var.name}-mysql-final"

  lifecycle {
    # Minor version tự nâng cấp (auto_minor_version_upgrade) sẽ không bị Terraform coi là drift.
    ignore_changes = [engine_version]
  }
}
