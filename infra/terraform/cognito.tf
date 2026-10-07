resource "aws_cognito_user_pool" "main" {
  name                     = local.name
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }
  # Tenant key. Admins set custom:org_id when creating users; it maps users to an organization.
  schema {
    name                = "org_id"
    attribute_data_type = "String"
    mutable             = true
    string_attribute_constraints {
      min_length = 1
      max_length = 64
    }
  }
  admin_create_user_config { allow_admin_create_user_only = true }
}

resource "aws_cognito_user_group" "roles" {
  for_each     = toset(["admin", "analyst", "viewer"])
  name         = each.value
  user_pool_id = aws_cognito_user_pool.main.id
}

resource "aws_cognito_user_pool_client" "web" {
  name                = "web"
  user_pool_id        = aws_cognito_user_pool.main.id
  generate_secret     = false
  explicit_auth_flows = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  read_attributes     = ["email", "custom:org_id"]
  id_token_validity   = 1
  token_validity_units { id_token = "hours" }
}
