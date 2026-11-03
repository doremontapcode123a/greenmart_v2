#!/usr/bin/env bash
# Bootstrap cho cluster EKS mới tạo, theo 3 hướng dẫn của AWS:
#   1) Tạo IAM OIDC provider cho cluster
#      https://docs.aws.amazon.com/eks/latest/userguide/enable-iam-roles-for-service-accounts.html
#   2) Cài AWS Load Balancer Controller bằng Helm
#      https://docs.aws.amazon.com/eks/latest/userguide/lbc-helm.html
#   3) Deploy ứng dụng mẫu 2048 (tạo ALB qua Ingress)
#      https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html#application-load-balancer-sample-application
#
# Idempotent: chạy lại nhiều lần an toàn (bước nào đã có thì bỏ qua / nâng cấp).
# Cấu hình hoàn toàn bằng biến môi trường (xem README.md). Bắt buộc: CLUSTER_NAME.
set -Eeuo pipefail

# ---------------------------- cấu hình ----------------------------
CLUSTER_NAME="${CLUSTER_NAME:-}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
ACTION="${ACTION:-install}"                           # install | delete-sample

LBC_VERSION="${LBC_VERSION:-v2.14.1}"                 # bản controller (policy + manifest mẫu) theo guide
LBC_CHART_VERSION="${LBC_CHART_VERSION:-1.14.0}"      # bản Helm chart theo guide
IAM_POLICY_NAME="${IAM_POLICY_NAME:-AWSLoadBalancerControllerIAMPolicy}"
UPDATE_IAM_POLICY="${UPDATE_IAM_POLICY:-false}"       # true: đẩy policy mới (default version) nếu policy đã tồn tại
SET_REGION_VPC="${SET_REGION_VPC:-false}"             # true: thêm --set region/vpcId (node hạn chế IMDS, Fargate, Hybrid)
FORCE_LBC="${FORCE_LBC:-false}"                       # true: vẫn cài LBC trên cluster EKS Auto Mode

INSTALL_GATEWAY_API_CRDS="${INSTALL_GATEWAY_API_CRDS:-true}"       # prerequisite của trang lbc-helm
GATEWAY_API_VERSION="${GATEWAY_API_VERSION:-v1.3.0}"
INSTALL_LBC_GATEWAY_CRDS="${INSTALL_LBC_GATEWAY_CRDS:-true}"       # CRD Gateway riêng của LBC (best-effort)

DEPLOY_SAMPLE="${DEPLOY_SAMPLE:-true}"
SAMPLE_SCHEME="${SAMPLE_SCHEME:-internet-facing}"     # internet-facing | internal
HTTP_CHECK="${HTTP_CHECK:-true}"                      # thử gọi HTTP vào ALB sau khi có địa chỉ

INSTALL_TOOLS="${INSTALL_TOOLS:-false}"               # true: tự tải kubectl/eksctl/helm còn thiếu (Linux)
KUBECTL_VERSION="${KUBECTL_VERSION:-}"                # rỗng = stable
HELM_VERSION="${HELM_VERSION:-v3.16.4}"
MIN_EKSCTL_VERSION="0.215.0"                          # yêu cầu của hướng dẫn OIDC

NODE_WAIT_TIMEOUT="${NODE_WAIT_TIMEOUT:-900}"         # giây chờ node Ready
INGRESS_WAIT_TIMEOUT="${INGRESS_WAIT_TIMEOUT:-900}"   # giây chờ ALB có địa chỉ
RETRY_SLEEP="${RETRY_SLEEP:-10}"

LBC_SA="aws-load-balancer-controller"
LBC_NS="kube-system"
SAMPLE_NS="game-2048"
SAMPLE_INGRESS="ingress-2048"
RAW="https://raw.githubusercontent.com"
LBC_REPO_RAW="${RAW}/kubernetes-sigs/aws-load-balancer-controller/${LBC_VERSION}"

# ---------------------------- tiện ích ----------------------------
log()  { printf '\n[%s] \033[1;34m==>\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
info() { printf '[%s]     %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '[%s] \033[1;33mWARN\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die()  { printf '[%s] \033[1;31mLỖI\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; exit 1; }
trap 'die "Thất bại ở dòng ${LINENO}: ${BASH_COMMAND}"' ERR

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

fetch() { curl -fsSL --retry 3 --retry-delay 2 -o "$2" "$1"; }

retry() {  # retry <số lần> <lệnh...>
  local n="$1" i; shift
  for ((i = 1; i <= n; i++)); do
    "$@" && return 0
    warn "Lần ${i}/${n} thất bại, thử lại sau ${RETRY_SLEEP}s: $*"
    sleep "$RETRY_SLEEP"
  done
  return 1
}

version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]; }  # $1 >= $2

arch() { case "$(uname -m)" in x86_64|amd64) echo amd64 ;; aarch64|arm64) echo arm64 ;; *) die "Kiến trúc không hỗ trợ: $(uname -m)" ;; esac; }

install_tool() {
  local tool="$1" bin="${HOME}/.local/bin" a; a="$(arch)"
  mkdir -p "$bin"; export PATH="$bin:$PATH"
  [ "$(uname -s)" = "Linux" ] || die "INSTALL_TOOLS chỉ hỗ trợ Linux; hãy tự cài ${tool}."
  log "Cài ${tool} vào ${bin}"
  case "$tool" in
    kubectl)
      local v="${KUBECTL_VERSION:-$(curl -fsSL https://dl.k8s.io/release/stable.txt)}"
      fetch "https://dl.k8s.io/release/${v}/bin/linux/${a}/kubectl" "$bin/kubectl"; chmod +x "$bin/kubectl" ;;
    eksctl)
      fetch "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_Linux_${a}.tar.gz" "$WORKDIR/eksctl.tgz"
      tar -xzf "$WORKDIR/eksctl.tgz" -C "$bin" eksctl ;;
    helm)
      fetch "https://get.helm.sh/helm-${HELM_VERSION}-linux-${a}.tar.gz" "$WORKDIR/helm.tgz"
      tar -xzf "$WORKDIR/helm.tgz" -C "$WORKDIR" "linux-${a}/helm"; mv "$WORKDIR/linux-${a}/helm" "$bin/helm"; chmod +x "$bin/helm" ;;
    *) die "Không biết cách cài ${tool}" ;;
  esac
}

need() {
  local tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 && continue
    if [ "$INSTALL_TOOLS" = "true" ] && [ "$tool" != "aws" ]; then install_tool "$tool"
    else die "Thiếu công cụ '${tool}'. Cài thủ công hoặc đặt INSTALL_TOOLS=true (aws CLI luôn phải cài sẵn)."; fi
  done
}

# ---------------------------- bước 0: chuẩn bị ----------------------------
preflight() {
  [ -n "$CLUSTER_NAME" ] || die "Chưa đặt CLUSTER_NAME."
  need aws kubectl eksctl helm curl
  local v; v="$(eksctl version 2>/dev/null | head -n1 | sed 's/-.*//; s/^v//')"
  if [ -n "$v" ] && ! version_ge "$v" "$MIN_EKSCTL_VERSION"; then
    die "eksctl ${v} quá cũ; hướng dẫn OIDC yêu cầu >= ${MIN_EKSCTL_VERSION}."
  fi

  ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
  log "Tài khoản AWS ${ACCOUNT_ID} | cluster '${CLUSTER_NAME}' | region ${AWS_REGION}"

  log "Chờ cluster ở trạng thái ACTIVE"
  aws eks wait cluster-active --name "$CLUSTER_NAME" --region "$AWS_REGION"
  aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION" >/dev/null
  VPC_ID="$(aws eks describe-cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" --query 'cluster.resourcesVpcConfig.vpcId' --output text)"

  local auto
  auto="$(aws eks describe-cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" --query 'cluster.computeConfig.enabled' --output text 2>/dev/null || true)"
  if [ "${auto,,}" = "true" ] && [ "$FORCE_LBC" != "true" ]; then
    die "Cluster dùng EKS Auto Mode: đã có sẵn load balancing, không cần cài LBC (AWS khuyến nghị bỏ qua). Đặt FORCE_LBC=true nếu vẫn muốn cài."
  fi

  log "Chờ node ở trạng thái Ready (tối đa ${NODE_WAIT_TIMEOUT}s)"
  local deadline=$((SECONDS + NODE_WAIT_TIMEOUT)) ready=0
  while ((SECONDS < deadline)); do
    ready="$(kubectl get nodes --no-headers 2>/dev/null | awk '$2 == "Ready" {c++} END {print c + 0}')"
    ((ready > 0)) && break
    sleep 15
  done
  ((ready > 0)) || die "Không có node Ready sau ${NODE_WAIT_TIMEOUT}s (cluster chưa có node group?)."
  info "${ready} node Ready"
}

# ---------------------------- bước 1: OIDC ----------------------------
step_oidc() {
  log "[1/3] IAM OIDC provider"
  local oidc_id
  oidc_id="$(aws eks describe-cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" --query 'cluster.identity.oidc.issuer' --output text | cut -d '/' -f 5)"
  [ -n "$oidc_id" ] && [ "$oidc_id" != "None" ] || die "Không lấy được OIDC issuer của cluster."
  info "OIDC issuer id: ${oidc_id}"
  if aws iam list-open-id-connect-providers | grep -q "$oidc_id"; then
    info "Đã có IAM OIDC provider cho cluster -> bỏ qua"
  else
    eksctl utils associate-iam-oidc-provider --cluster "$CLUSTER_NAME" --region "$AWS_REGION" --approve
  fi
}

# ---------------------------- bước 2: AWS Load Balancer Controller ----------------------------
update_iam_policy() {
  local arn="$1" file="$2" count oldest
  count="$(aws iam list-policy-versions --policy-arn "$arn" --query 'length(Versions)' --output text)"
  if [ "$count" -ge 5 ]; then  # IAM giới hạn 5 version: xóa version cũ nhất không phải default
    # shellcheck disable=SC2016  # dấu backtick là cú pháp JMESPath, không phải command substitution
    oldest="$(aws iam list-policy-versions --policy-arn "$arn" --query 'sort_by(Versions[?IsDefaultVersion==`false`], &CreateDate)[0].VersionId' --output text)"
    aws iam delete-policy-version --policy-arn "$arn" --version-id "$oldest"
  fi
  aws iam create-policy-version --policy-arn "$arn" --policy-document "file://${file}" --set-as-default >/dev/null
}

step_lbc() {
  log "[2/3] AWS Load Balancer Controller ${LBC_VERSION} (chart ${LBC_CHART_VERSION})"

  if [ "$INSTALL_GATEWAY_API_CRDS" = "true" ]; then
    info "Cài Gateway API CRDs ${GATEWAY_API_VERSION} (prerequisite của trang lbc-helm)"
    retry 3 kubectl apply --server-side -f "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml"
    if [ "$INSTALL_LBC_GATEWAY_CRDS" = "true" ]; then
      kubectl apply --server-side -f "${LBC_REPO_RAW}/config/crd/gateway/gateway-crds.yaml" \
        || warn "Không cài được CRD Gateway của LBC (không ảnh hưởng Ingress/ALB); tiếp tục."
    fi
  fi

  local policy_arn="arn:aws:iam::${ACCOUNT_ID}:policy/${IAM_POLICY_NAME}"
  fetch "${LBC_REPO_RAW}/docs/install/iam_policy.json" "$WORKDIR/iam_policy.json"
  if aws iam get-policy --policy-arn "$policy_arn" >/dev/null 2>&1; then
    if [ "$UPDATE_IAM_POLICY" = "true" ]; then info "Cập nhật IAM policy ${IAM_POLICY_NAME}"; update_iam_policy "$policy_arn" "$WORKDIR/iam_policy.json"
    else info "IAM policy ${IAM_POLICY_NAME} đã có -> bỏ qua (UPDATE_IAM_POLICY=true để cập nhật theo ${LBC_VERSION})"; fi
  else
    info "Tạo IAM policy ${IAM_POLICY_NAME}"
    aws iam create-policy --policy-name "$IAM_POLICY_NAME" --policy-document "file://${WORKDIR}/iam_policy.json" >/dev/null
  fi

  if eksctl get iamserviceaccount --cluster "$CLUSTER_NAME" --region "$AWS_REGION" --namespace "$LBC_NS" --name "$LBC_SA" 2>/dev/null | grep -q "$LBC_SA"; then
    info "ServiceAccount ${LBC_NS}/${LBC_SA} (IRSA) đã có -> bỏ qua"
  else
    eksctl create iamserviceaccount \
      --cluster="$CLUSTER_NAME" --namespace="$LBC_NS" --name="$LBC_SA" \
      --attach-policy-arn="$policy_arn" --override-existing-serviceaccounts \
      --region "$AWS_REGION" --approve
  fi

  helm repo add eks https://aws.github.io/eks-charts --force-update >/dev/null
  helm repo update eks >/dev/null

  if helm status "$LBC_SA" -n "$LBC_NS" >/dev/null 2>&1; then
    info "Đã cài Helm release -> nâng cấp (helm upgrade không cập nhật CRD nên áp CRD thủ công như guide)"
    retry 3 kubectl apply -f "${RAW}/aws/eks-charts/master/stable/aws-load-balancer-controller/crds/crds.yaml"
  fi

  local args=(-n "$LBC_NS" --set "clusterName=${CLUSTER_NAME}" --set serviceAccount.create=false
              --set "serviceAccount.name=${LBC_SA}" --version "$LBC_CHART_VERSION")
  if [ "$SET_REGION_VPC" = "true" ]; then args+=(--set "region=${AWS_REGION}" --set "vpcId=${VPC_ID}"); fi
  helm upgrade --install "$LBC_SA" eks/aws-load-balancer-controller "${args[@]}" --wait --timeout 10m

  kubectl rollout status "deployment/${LBC_SA}" -n "$LBC_NS" --timeout=300s
  kubectl get deployment -n "$LBC_NS" "$LBC_SA"
}

# ---------------------------- bước 3: ứng dụng mẫu 2048 ----------------------------
sample_manifest() {
  fetch "${LBC_REPO_RAW}/docs/examples/2048/2048_full.yaml" "$WORKDIR/2048_full.yaml"
  if [ "$SAMPLE_SCHEME" = "internal" ]; then
    sed -i 's#alb.ingress.kubernetes.io/scheme: internet-facing#alb.ingress.kubernetes.io/scheme: internal#' "$WORKDIR/2048_full.yaml"
  fi
}

step_sample() {
  log "[3/3] Ứng dụng mẫu 2048 (${SAMPLE_SCHEME})"
  case "$SAMPLE_SCHEME" in internet-facing|internal) ;; *) die "SAMPLE_SCHEME phải là internet-facing hoặc internal" ;; esac

  if [ "$SAMPLE_SCHEME" = "internet-facing" ]; then
    local tagged
    tagged="$(aws ec2 describe-subnets --region "$AWS_REGION" --filters "Name=vpc-id,Values=${VPC_ID}" "Name=tag:kubernetes.io/role/elb,Values=1" --query 'length(Subnets)' --output text)"
    [ "${tagged:-0}" -ge 2 ] || warn "VPC chỉ có ${tagged:-0} public subnet gắn tag kubernetes.io/role/elb=1 (cần >= 2 subnet ở 2 AZ); ALB có thể không tạo được."
  fi

  sample_manifest
  # Webhook của controller có thể chưa sẵn sàng ngay sau khi rollout -> thử lại.
  retry 6 kubectl apply -f "$WORKDIR/2048_full.yaml"

  log "Chờ ALB được tạo (tối đa ${INGRESS_WAIT_TIMEOUT}s)"
  local deadline=$((SECONDS + INGRESS_WAIT_TIMEOUT)) addr=""
  while ((SECONDS < deadline)); do
    addr="$(kubectl get ingress "$SAMPLE_INGRESS" -n "$SAMPLE_NS" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
    [ -n "$addr" ] && break
    sleep 15
  done
  if [ -z "$addr" ]; then
    warn "Ingress chưa có địa chỉ. Log của controller:"
    kubectl logs -n "$LBC_NS" -l "app.kubernetes.io/instance=${LBC_SA}" --tail=50 || true
    die "ALB không được tạo trong ${INGRESS_WAIT_TIMEOUT}s."
  fi
  kubectl get ingress "$SAMPLE_INGRESS" -n "$SAMPLE_NS"
  SAMPLE_URL="http://${addr}"

  if [ "$HTTP_CHECK" = "true" ] && [ "$SAMPLE_SCHEME" = "internet-facing" ]; then
    local i code
    for i in $(seq 1 20); do
      code="$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$SAMPLE_URL" || true)"
      [ "$code" = "200" ] && { info "HTTP 200 từ ${SAMPLE_URL}"; return 0; }
      info "Chờ ALB sẵn sàng nhận request (lần ${i}, mã ${code:-000})"; sleep 15
    done
    warn "ALB đã có địa chỉ nhưng chưa trả HTTP 200; thử lại bằng trình duyệt sau ít phút."
  fi
}

delete_sample() {
  log "Xóa ứng dụng mẫu 2048 (ALB sẽ được controller xóa theo)"
  sample_manifest
  kubectl delete -f "$WORKDIR/2048_full.yaml" --ignore-not-found
}

# ---------------------------- main ----------------------------
main() {
  preflight
  case "$ACTION" in
    install)
      step_oidc
      step_lbc
      if [ "$DEPLOY_SAMPLE" = "true" ]; then step_sample; else info "Bỏ qua ứng dụng mẫu (DEPLOY_SAMPLE=false)"; fi
      log "HOÀN TẤT"
      info "OIDC provider: OK | AWS Load Balancer Controller: OK"
      [ -z "${SAMPLE_URL:-}" ] || info "Ứng dụng 2048: ${SAMPLE_URL}   (xóa khi test xong: ACTION=delete-sample)"
      if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
        { echo "### EKS bootstrap: ${CLUSTER_NAME} (${AWS_REGION})"; echo "- OIDC provider: OK"; echo "- AWS Load Balancer Controller: OK";
          [ -z "${SAMPLE_URL:-}" ] || echo "- 2048: ${SAMPLE_URL}"; } >> "$GITHUB_STEP_SUMMARY"
      fi
      ;;
    delete-sample) delete_sample ;;
    *) die "ACTION không hợp lệ: ${ACTION} (install | delete-sample)" ;;
  esac
}
main "$@"
