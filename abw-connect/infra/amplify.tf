# Frontend hosting: a repository-less Amplify app deployed by zip upload, like live.
# Terraform creates the app and the main branch only. The static export is uploaded
# with `aws amplify create-deployment` / `start-deployment` (see README.md), because
# Terraform cannot upload a deployment zip.
#
# Which app is built and uploaded is chosen per environment by var.frontend_app
# ("frontend" or "builder-compass"); the deploy workflow reads it from the frontend_app output.
#
# Basic Auth is deliberately NOT managed here: aws_amplify_branch stores the
# credentials in Terraform state. Enable it outside Terraform if you need it.
locals {
  amplify_custom_rules = {
    # The original ABW Connect frontend (a single-page app): SPA rewrites, copied from live.
    # Unchanged, in the same order, so environments that keep this frontend see no diff.
    "frontend" = [
      {
        source = "/<*>"
        target = "/index.html"
        status = "404-200"
      },
      {
        source = "</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json)$)([^.]+$)/>"
        target = "/index.html"
        status = "200"
      },
    ]

    # Builder Compass: a multi-page static export built with trailingSlash, so every page is a
    # folder with an index.html (/ask/, /advisor/, /session/<id>/) that Amplify serves as is.
    # The SPA rules above must NOT be used here: they would turn every page into the home page.
    "builder-compass" = [
      {
        source = "/report"
        target = "/notes/"
        status = "301"
      },
      {
        source = "/report/"
        target = "/notes/"
        status = "301"
      },
      # Deliberately no "/<*>" 404 rule: a catch-all 404 rule stops Amplify's automatic
      # /ask -> /ask/ clean-URL redirect. Unknown paths get Amplify's default 404.
    ]
  }
}

resource "aws_amplify_app" "frontend" {
  count = var.create_amplify ? 1 : 0

  name     = "${var.name_prefix}-frontend"
  platform = "WEB"

  # Rewrite rules depend on which frontend this environment hosts (var.frontend_app), see the locals above.
  dynamic "custom_rule" {
    for_each = local.amplify_custom_rules[var.frontend_app]
    content {
      source = custom_rule.value.source
      target = custom_rule.value.target
      status = custom_rule.value.status
    }
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
