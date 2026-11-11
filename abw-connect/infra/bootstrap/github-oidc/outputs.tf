# Role ARNs go into GitHub (environment secret AWS_ROLE_ARN, repository secret AWS_PLAN_ROLE_ARN).
# They are never committed.
output "staging_deploy_role_arn" {
  description = "-> secret AWS_ROLE_ARN in the `staging` GitHub environment"
  value       = aws_iam_role.deploy["staging"].arn
}

output "prod_deploy_role_arn" {
  description = "-> secret AWS_ROLE_ARN in the `production` GitHub environment"
  value       = aws_iam_role.deploy["prod"].arn
}

output "plan_role_arn" {
  description = "-> repository secret AWS_PLAN_ROLE_ARN"
  value       = aws_iam_role.plan.arn
}

output "boundary_policy_names" {
  value = { for k, p in aws_iam_policy.boundary : k => p.name }
}
