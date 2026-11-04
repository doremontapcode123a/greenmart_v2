variable "region" {
  description = "AWS region của cluster EKS."
  type        = string
  default     = "ap-southeast-1"
}

variable "cluster_name" {
  description = "Tên cluster EKS đã có sẵn (RDS sẽ được đặt cùng VPC với cluster này)."
  type        = string
}

variable "name" {
  description = "Tiền tố đặt tên tài nguyên."
  type        = string
  default     = "greenmart"
}

# ---------- RDS ----------
variable "db_subnet_ids" {
  description = "Subnet (private) cho RDS, tối thiểu 2 AZ. Để trống = tự tìm subnet có tag kubernetes.io/role/internal-elb=1 trong VPC của cluster."
  type        = list(string)
  default     = []
}

variable "db_engine_version" {
  description = "Phiên bản MySQL. Dùng 8.0 (8.4 tắt mysql_native_password mặc định, script tạo user của dự án sẽ lỗi)."
  type        = string
  default     = "8.0"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "db_allocated_storage" {
  description = "Dung lượng ban đầu (GiB)."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Giới hạn tự động mở rộng dung lượng (GiB). 0 = tắt autoscaling storage."
  type        = number
  default     = 100
}

variable "db_master_username" {
  type    = string
  default = "admin"
}

variable "db_multi_az" {
  description = "Bật Multi-AZ (khuyến nghị cho production, tốn gấp đôi chi phí instance)."
  type        = bool
  default     = false
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

variable "db_skip_final_snapshot" {
  description = "true = KHÔNG chụp snapshot cuối khi xóa DB (chỉ nên dùng cho môi trường thử)."
  type        = bool
  default     = false
}

# ---------- EBS ----------
variable "install_ebs_csi_addon" {
  description = "Cài addon aws-ebs-csi-driver + IAM role (IRSA). Đặt false nếu cluster đã có addon này."
  type        = bool
  default     = true
}

variable "ebs_snapshot_retention" {
  description = "Số snapshot EBS hằng ngày được giữ lại (cho volume có tag greenmart-backup=true)."
  type        = number
  default     = 7
}

# ---------- Secret + 5 database trong cluster ----------
variable "k8s_namespace" {
  description = "Namespace của ứng dụng (khớp k8s/base/namespace.yaml)."
  type        = string
  default     = "greenmart"
}

variable "email_host_password" {
  description = "Mật khẩu SMTP gửi mail đặt lại mật khẩu (để trống nếu chưa dùng)."
  type        = string
  default     = ""
  sensitive   = true
}
variable "enable_monitoring" {
  description = "Tạo addon CloudWatch Container Insights, role IRSA (Grafana, X-Ray daemon) và luật lấy mẫu X-Ray."
  type        = bool
  default     = true
}

variable "xray_sample_rate" {
  description = "Tỉ lệ lấy mẫu trace X-Ray cho request thường (1 = ghi 100%, dùng khi so sánh số request với Prometheus; hạ xuống để giảm chi phí)."
  type        = number
  default     = 1
}
