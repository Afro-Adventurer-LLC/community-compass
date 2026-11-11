# Four on-demand tables, same keys and indexes as live. The app derives the names
# from DDB_TABLE_PREFIX (<prefix>-conversations, -turns, -feedback, -unanswered).
resource "aws_dynamodb_table" "conversations" {
  name         = "${var.name_prefix}-conversations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "turns" {
  name         = "${var.name_prefix}-turns"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "conversation_id"
  range_key    = "turn_no"

  attribute {
    name = "conversation_id"
    type = "S"
  }

  attribute {
    name = "turn_no"
    type = "N"
  }
}

resource "aws_dynamodb_table" "feedback" {
  name         = "${var.name_prefix}-feedback"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "unanswered" {
  name         = "${var.name_prefix}-unanswered"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "status-created_at-index"
    projection_type = "ALL"

    key_schema {
      attribute_name = "status"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "created_at"
      key_type       = "RANGE"
    }
  }
}
