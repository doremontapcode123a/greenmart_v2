# X-Ray daemon + PodMonitor GreenMart + dashboard so sánh (đọc từ Git: gitops/monitoring/extras).
# Patch inline gắn role IRSA và AWS_REGION cho X-Ray daemon. File mẫu: workflow thay ${...} bằng envsubst.
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: monitoring-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  ignoreDifferences:
    - group: monitoring.coreos.com
      kind: PodMonitor
      jqPathExpressions:
        - .spec.podMetricsEndpoints[]?.relabelings[]?.action
  source:
    repoURL: ${REPO_URL}
    targetRevision: ${REPO_REVISION}
    path: gitops/monitoring/extras
    kustomize:
      patches:
        - target:
            kind: ServiceAccount
            name: xray-daemon
          patch: |-
            apiVersion: v1
            kind: ServiceAccount
            metadata:
              name: xray-daemon
              annotations:
                eks.amazonaws.com/role-arn: ${XRAY_ROLE_ARN}
        - target:
            kind: Deployment
            name: xray-daemon
          patch: |-
            - op: add
              path: /spec/template/spec/containers/0/env
              value:
                - name: AWS_REGION
                  value: ${AWS_REGION}
  destination:
    server: https://kubernetes.default.svc
    namespace: monitoring
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
      - SkipDryRunOnMissingResource=true   # PodMonitor cần CRD do monitoring-stack cài; Argo thử lại tới khi CRD có
    retry:
      limit: 10
      backoff:
        duration: 20s
        factor: 2
        maxDuration: 5m
