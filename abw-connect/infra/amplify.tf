# Frontend hosting: a repository-less Amplify app deployed by zip upload, like live.
# Terraform creates the app and the main branch only. The static export is uploaded
# with `aws amplify create-deployment` / `start-deployment` (see README.md), because
# Terraform cannot upload a deployment zip.
#
# Basic Auth is deliberately NOT managed here: aws_amplify_branch stores the
# credentials in Terraform state. Enable it outside Terraform if you need it.
resource "aws_amplify_app" "frontend" {
  count = var.create_amplify ? 1 : 0

  name     = "${var.name_prefix}-frontend"
  platform = "WEB"

  # SPA rewrites, copied from live.
  custom_rule {
    source = "/<*>"
    target = "/index.html"
    status = "404-200"
  }

  custom_rule {
    source = "</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json)$)([^.]+$)/>"
    target = "/index.html"
    status = "200"
  }

  # The static bundle bakes this in at build time (NEXT_PUBLIC_API_URL).
  environment_variables = {
    NEXT_PUBLIC_API_URL = aws_apigatewayv2_api.http.api_endpoint
  }
}

resource "aws_amplify_branch" "main" {
  count = var.create_amplify ? 1 : 0

  app_id            = aws_amplify_app.frontend[0].id
  branch_name       = "main"
  stage             = "PRODUCTION"
  framework         = "Next.js - Static"
  enable_auto_build = true
}
