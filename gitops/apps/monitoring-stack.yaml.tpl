# Prometheus + Grafana (chart kube-prometheus-stack) do Argo CD cài. File mẫu: workflow (eks-step8-monitoring.yml) thay ${...} bằng envsubst.
# Grafana có sẵn 3 datasource: Prometheus, CloudWatch, X-Ray (đọc bằng role IRSA ${GRAFANA_ROLE_ARN}).
# Mật khẩu admin Grafana nằm trong Secret grafana-admin (workflow tạo, ngẫu nhiên).
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: monitoring-stack
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://prometheus-community.github.io/helm-charts
    chart: kube-prometheus-stack
    targetRevision: 92.17.1
    helm:
      releaseName: kps
      valuesObject:
        alertmanager:
          enabled: false          # chưa cấu hình kênh cảnh báo; bật lại khi cần
        prometheus:
          prometheusSpec:
            retention: 7d
            # Nhận PodMonitor/ServiceMonitor ở mọi namespace (PodMonitor của GreenMart nằm ở gitops/monitoring/extras)
            podMonitorSelectorNilUsesHelmValues: false
            serviceMonitorSelectorNilUsesHelmValues: false
            resources:
              requests: { cpu: 200m, memory: 768Mi }
              limits: { memory: 1536Mi }
            storageSpec:
              volumeClaimTemplate:
                spec:
                  storageClassName: ebs-gp3
                  accessModes: [ReadWriteOnce]
                  resources:
                    requests:
                      storage: 10Gi
        prometheusOperator:
          resources:
            requests: { cpu: 50m, memory: 64Mi }
            limits: { memory: 256Mi }
        grafana:
          enabled: true
          admin:
            existingSecret: grafana-admin
            userKey: admin-user
            passwordKey: admin-password
          serviceAccount:
            create: true
            name: grafana
            annotations:
              eks.amazonaws.com/role-arn: ${GRAFANA_ROLE_ARN}
          plugins:
            - grafana-x-ray-datasource
          resources:
            requests: { cpu: 50m, memory: 192Mi }
            limits: { memory: 512Mi }
          additionalDataSources:
            - name: CloudWatch
              type: cloudwatch
              uid: cloudwatch
              access: proxy
              jsonData:
                authType: default
                defaultRegion: ${AWS_REGION}
            - name: X-Ray
              type: grafana-x-ray-datasource
              uid: xray
              access: proxy
              jsonData:
                authType: default
                defaultRegion: ${AWS_REGION}
        kube-state-metrics:
          resources:
            requests: { cpu: 20m, memory: 64Mi }
            limits: { memory: 192Mi }
        prometheus-node-exporter:
          resources:
            requests: { cpu: 20m, memory: 32Mi }
            limits: { memory: 96Mi }
  destination:
    server: https://kubernetes.default.svc
    namespace: monitoring
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true      # CRD của Prometheus operator rất lớn, cần server-side apply
    retry:
      limit: 5
      backoff:
        duration: 15s
        factor: 2
        maxDuration: 5m
