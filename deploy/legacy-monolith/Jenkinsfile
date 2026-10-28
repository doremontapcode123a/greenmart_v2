pipeline {
    agent any

    environment {
        // Cấu hình AWS & ECR
        AWS_REGION      = 'ap-southeast-1'
        AWS_ACCOUNT_ID  = '410098332444' // Thay bằng Account ID của bạn
        ECR_REGISTRY    = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
        
        // Tên repository trên ECR
        WEB_REPO        = 'greenmart-app'
        NGINX_REPO      = 'greenmart-nginx'
        
        // Cấu hình ECS
        CLUSTER_NAME    = 'greenmart-cluster'
        SERVICE_NAME    = 'greenmart-service'
        TASK_FAMILY     = 'greenmart-task'
        
        // Dùng Build Number của Jenkins làm Image Tag để dễ tracking
        IMAGE_TAG       = "${env.BUILD_NUMBER}" 
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Login to AWS ECR') {
            steps {
                // Yêu cầu Jenkins server đã được cài AWS CLI và có quyền IAM để pull/push ECR
                sh "aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}"
            }
        }

        stage('Build Docker Images') {
            steps {
                // Build Web Image
                sh "docker build -t ${ECR_REGISTRY}/${WEB_REPO}:${IMAGE_TAG} -t ${ECR_REGISTRY}/${WEB_REPO}:latest ."
                
                // Build Nginx Image (trỏ vào thư mục ./nginx)
                sh "docker build -f nginx/Dockerfile -t ${ECR_REGISTRY}/${NGINX_REPO}:${IMAGE_TAG} -t ${ECR_REGISTRY}/${NGINX_REPO}:latest ."
            }
        }

        stage('Push to ECR') {
            steps {
                // Push Web
                sh "docker push ${ECR_REGISTRY}/${WEB_REPO}:${IMAGE_TAG}"
                sh "docker push ${ECR_REGISTRY}/${WEB_REPO}:latest"
                
                // Push Nginx
                sh "docker push ${ECR_REGISTRY}/${NGINX_REPO}:${IMAGE_TAG}"
                sh "docker push ${ECR_REGISTRY}/${NGINX_REPO}:latest"
            }
        }

        stage('Deploy to ECS') {
            steps {
                script {
                    // 1. Dùng lệnh 'sed' để thay thế placeholder trong file JSON bằng URL ECR thực tế
                    sh """
                    sed -e "s|{{WEB_IMAGE}}|${ECR_REGISTRY}/${WEB_REPO}:${IMAGE_TAG}|g" \
                        -e "s|{{NGINX_IMAGE}}|${ECR_REGISTRY}/${NGINX_REPO}:${IMAGE_TAG}|g" \
                        taskdef-template.json > taskdef.json
                    """

                    // 2. Đăng ký Task Definition mới với AWS
                    sh """
                    aws ecs register-task-definition \
                        --cli-input-json file://taskdef.json \
                        --region ${AWS_REGION}
                    """

                    // 3. Update ECS Service để sử dụng bản Revision mới nhất của Task Family
                    sh """
                    aws ecs update-service \
                        --cluster ${CLUSTER_NAME} \
                        --service ${SERVICE_NAME} \
                        --desired-count 1 \
                        --task-definition ${TASK_FAMILY} \
                        --force-new-deployment \
                        --region ${AWS_REGION}
                    """
                }
            }
        }
    }
}