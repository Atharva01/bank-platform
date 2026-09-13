# Static public IP that survives instance stop/start, unlike the default
# ephemeral public IP. Point the domain's A record at this (registrar-
# agnostic - Route 53 isn't required).
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"

  tags = {
    Name = "bank-platform"
  }
}
