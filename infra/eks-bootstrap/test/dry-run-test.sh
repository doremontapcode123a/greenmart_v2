#!/usr/bin/env bash
# Chạy bootstrap.sh với aws/eksctl/kubectl/helm GIẢ để kiểm tra luồng logic (không đụng AWS thật).
# Cần internet (script vẫn tải policy/manifest từ GitHub). Dùng:  bash infra/eks-bootstrap/test/dry-run-test.sh
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
BIN="$TMP/bin"; mkdir -p "$BIN"; export FAKE_LOG="$TMP/calls.log"

cat > "$BIN/aws" <<'S'
#!/usr/bin/env bash
echo "aws $*" >> "$FAKE_LOG"
case "$*" in
  "sts get-caller-identity"*) echo 111122223333 ;;
  *"--query cluster.identity.oidc.issuer"*) echo "https://oidc.eks.ap-southeast-1.amazonaws.com/id/ABCDEF0123456789" ;;
  *"--query cluster.resourcesVpcConfig.vpcId"*) echo vpc-0abc ;;
  *"--query cluster.computeConfig.enabled"*) echo "${FAKE_AUTOMODE:-None}" ;;
  "iam list-open-id-connect-providers"*) [ -n "${FAKE_OIDC_EXISTS:-}" ] && echo '"Arn": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/ABCDEF0123456789"' || echo '{"OpenIDConnectProviderList": []}' ;;
  "iam get-policy"*) [ -n "${FAKE_POLICY_EXISTS:-}" ] || exit 254 ;;
  "iam list-policy-versions"*"length(Versions)"*) echo 5 ;;
  "iam list-policy-versions"*) echo v1 ;;
  "ec2 describe-subnets"*) echo 2 ;;
esac
exit 0
S
cat > "$BIN/eksctl" <<'S'
#!/usr/bin/env bash
echo "eksctl $*" >> "$FAKE_LOG"
case "$*" in
  version) echo 0.215.0 ;;
  "get iamserviceaccount"*) [ -n "${FAKE_SA_EXISTS:-}" ] && echo "kube-system aws-load-balancer-controller arn:aws:iam::111122223333:role/x" ;;
esac
exit 0
S
cat > "$BIN/helm" <<'S'
#!/usr/bin/env bash
echo "helm $*" >> "$FAKE_LOG"
case "$1" in status) [ -n "${FAKE_HELM_EXISTS:-}" ] || exit 1 ;; esac
exit 0
S
cat > "$BIN/kubectl" <<'S'
#!/usr/bin/env bash
echo "kubectl $*" >> "$FAKE_LOG"
case "$*" in
  "get nodes"*) echo "ip-10-0-1-5 Ready <none> 5m v1.31.0" ;;
  "get ingress"*jsonpath*) echo "k8s-game2048-ingress2-0123456789-9876543210.ap-southeast-1.elb.amazonaws.com" ;;
esac
exit 0
S
chmod +x "$BIN"/*

run() {  # run <tên> [VAR=giá_trị ...]
  local name="$1"; shift
  : > "$FAKE_LOG"
  echo "=== ${name}"
  env PATH="$BIN:$PATH" CLUSTER_NAME=demo AWS_REGION=ap-southeast-1 HTTP_CHECK=false RETRY_SLEEP=1 "$@" \
    bash "$HERE/../bootstrap.sh" > "$TMP/out.log" 2>&1 || { cat "$TMP/out.log"; echo "FAIL: ${name}"; exit 1; }
}
has()  { grep -qE -- "$1" "$FAKE_LOG" || { echo "FAIL: thiếu lệnh khớp /$1/"; cat "$FAKE_LOG"; exit 1; }; }
hasnt(){ ! grep -qE -- "$1" "$FAKE_LOG" || { echo "FAIL: không được có lệnh khớp /$1/"; exit 1; }; }
order(){ local a b; a=$(grep -nE -- "$1" "$FAKE_LOG" | head -1 | cut -d: -f1); b=$(grep -nE -- "$2" "$FAKE_LOG" | head -1 | cut -d: -f1)
         [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ] || { echo "FAIL: sai thứ tự /$1/ -> /$2/"; exit 1; }; }

# 1) Cluster mới: mọi thứ chưa có
run "cluster mới"
has  "eksctl utils associate-iam-oidc-provider --cluster demo --region ap-southeast-1 --approve"
has  "kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml"
has  "aws iam create-policy --policy-name AWSLoadBalancerControllerIAMPolicy"
has  "eksctl create iamserviceaccount --cluster=demo --namespace=kube-system --name=aws-load-balancer-controller --attach-policy-arn=arn:aws:iam::111122223333:policy/AWSLoadBalancerControllerIAMPolicy --override-existing-serviceaccounts"
has  "helm repo add eks https://aws.github.io/eks-charts"
has  "helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller -n kube-system --set clusterName=demo --set serviceAccount.create=false --set serviceAccount.name=aws-load-balancer-controller --version 1.14.0"
has  "kubectl apply -f .*2048_full.yaml"
hasnt "eks-charts/master/stable/aws-load-balancer-controller/crds/crds.yaml"
order "associate-iam-oidc-provider" "create iamserviceaccount"
order "create iamserviceaccount" "helm upgrade --install"
order "helm upgrade --install" "2048_full.yaml"
grep -q "Ứng dụng 2048: http://k8s-game2048" "$TMP/out.log" || { echo "FAIL: không in URL"; exit 1; }

# 2) Chạy lại: mọi thứ đã có -> không tạo lại, helm upgrade kèm CRD
run "chạy lại (idempotent)" FAKE_OIDC_EXISTS=1 FAKE_POLICY_EXISTS=1 FAKE_SA_EXISTS=1 FAKE_HELM_EXISTS=1
hasnt "associate-iam-oidc-provider"
hasnt "iam create-policy"
hasnt "create iamserviceaccount"
has   "kubectl apply -f https://raw.githubusercontent.com/aws/eks-charts/master/stable/aws-load-balancer-controller/crds/crds.yaml"
has   "helm upgrade --install"

# 3) Tuỳ chọn: cập nhật policy, internal, region/vpc, không sample
run "tuỳ chọn" FAKE_POLICY_EXISTS=1 UPDATE_IAM_POLICY=true SAMPLE_SCHEME=internal SET_REGION_VPC=true
has "aws iam delete-policy-version"
has "aws iam create-policy-version .* --set-as-default"
has "--set region=ap-southeast-1 --set vpcId=vpc-0abc"
run "không sample" DEPLOY_SAMPLE=false
hasnt "2048_full.yaml"

# 4) Xóa sample
run "delete-sample" ACTION=delete-sample
has "kubectl delete -f .*2048_full.yaml --ignore-not-found"
hasnt "helm upgrade"

# 5) Auto Mode bị từ chối; thiếu CLUSTER_NAME bị từ chối
: > "$FAKE_LOG"; echo "=== Auto Mode"
if env PATH="$BIN:$PATH" CLUSTER_NAME=demo FAKE_AUTOMODE=True bash "$HERE/../bootstrap.sh" >"$TMP/out.log" 2>&1; then echo "FAIL: Auto Mode phải bị từ chối"; exit 1; fi
grep -q "EKS Auto Mode" "$TMP/out.log"
echo "=== thiếu CLUSTER_NAME"
if env PATH="$BIN:$PATH" CLUSTER_NAME= bash "$HERE/../bootstrap.sh" >"$TMP/out.log" 2>&1; then echo "FAIL"; exit 1; fi
grep -q "Chưa đặt CLUSTER_NAME" "$TMP/out.log"
echo; echo "ALL TESTS PASSED"
