# Argo CD Application cho ứng dụng GreenMart. File mẫu: workflow (eks-step5-deploy.yml) thay các biến ${...} bằng envsubst rồi `kubectl apply`.
# Argo CD đọc manifest thật từ Git (k8s/overlays/eks); các giá trị riêng của môi trường (ECR, tag, DB_HOST, địa chỉ ALB)
# nằm ở đây dưới dạng kustomize override, không phải sửa kustomization.yaml trong Git.
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: greenmart
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: ${REPO_URL}
    targetRevision: ${REPO_REVISION}
    path: k8s/overlays/eks
    kustomize:
      images:
        - registry.example.com/greenmart/user-service=${ECR_REGISTRY}/greenmart/user-service:${IMAGE_TAG}
        - registry.example.com/greenmart/catalog-service=${ECR_REGISTRY}/greenmart/catalog-service:${IMAGE_TAG}
        - registry.example.com/greenmart/order-service=${ECR_REGISTRY}/greenmart/order-service:${IMAGE_TAG}
        - registry.example.com/greenmart/promotion-service=${ECR_REGISTRY}/greenmart/promotion-service:${IMAGE_TAG}
        - registry.example.com/greenmart/web=${ECR_REGISTRY}/greenmart/web:${IMAGE_TAG}
      patches:
        - target:
            kind: ConfigMap
            name: greenmart-config
          patch: |-
            apiVersion: v1
            kind: ConfigMap
            metadata:
              name: greenmart-config
            data:
              DB_HOST: ${DB_HOST}
              PUBLIC_HOST: ${PUBLIC_HOST}
              CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS}
        # Ingress (ALB) đợi tới wave 2: ALB tạo mất vài phút và không được chặn các Job migrate ở wave 1.
        - target:
            kind: Ingress
            name: greenmart-alb
          patch: |-
            - op: add
              path: /metadata/annotations/argocd.argoproj.io~1sync-wave
              value: "2"
        # Job migrate chạy như hook của Argo CD (sau khi ConfigMap/Deployment đã lên), tạo lại mỗi lần sync.
        - target:
            kind: Job
            labelSelector: app.kubernetes.io/component=migrate
          patch: |-
            - op: add
              path: /metadata/annotations
              value:
                argocd.argoproj.io/hook: Sync
                argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
                argocd.argoproj.io/sync-wave: "1"
  destination:
    server: https://kubernetes.default.svc
    namespace: greenmart
  ignoreDifferences:
    # HPA điều chỉnh replicas; `kubectl rollout restart` thêm annotation restartedAt: đều không phải drift.
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas
        - /spec/template/metadata/annotations/kubectl.kubernetes.io~1restartedAt
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
    retry:
      limit: 5
      backoff:
        duration: 10s
        factor: 2
        maxDuration: 3m
