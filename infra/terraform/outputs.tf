output "rds_address" {
  description = "Điền vào DB_HOST trong k8s/overlays/eks/kustomization.yaml"
  value       = aws_db_instance.mysql.address
}

output "rds_port" {
  value = aws_db_instance.mysql.port
}

output "rds_master_secret_arn" {
  description = "Secret trong AWS Secrets Manager chứa mật khẩu master do RDS tự sinh (key: username, password)."
  value       = aws_db_instance.mysql.master_user_secret[0].secret_arn
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "ebs_csi_role_arn" {
  value = try(aws_iam_role.ebs_csi[0].arn, null)
}

output "next_steps" {
  value = <<-EOT
    1) Lấy mật khẩu master RDS (để tạo K8s Secret RDS_ADMIN_PASSWORD):
       aws secretsmanager get-secret-value --region ${var.region} --secret-id ${aws_db_instance.mysql.master_user_secret[0].secret_arn} --query SecretString --output text
    2) Sửa DB_HOST trong k8s/overlays/eks/kustomization.yaml thành: ${aws_db_instance.mysql.address}
    3) kubectl apply -k k8s/overlays/eks   (xem k8s/overlays/eks/README.md)
  EOT
}
