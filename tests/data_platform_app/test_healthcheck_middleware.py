ELB_USER_AGENT = "ELB-HealthChecker/2.0"
IP_HOST = "10.199.1.23"


class TestHealthCheckHostMiddleware:
    """Tests for the ALB IP-host health-check short-circuit."""

    def test_elb_healthcheck_with_ip_host_returns_200(self, client):
        response = client.get(
            "/healthcheck/",
            HTTP_HOST=IP_HOST,
            HTTP_USER_AGENT=ELB_USER_AGENT,
        )

        assert response.status_code == 200
        assert response.content == b"OK"

    def test_healthcheck_with_ip_host_but_normal_user_agent_is_blocked(self, client):
        response = client.get(
            "/healthcheck/",
            HTTP_HOST=IP_HOST,
            HTTP_USER_AGENT="Mozilla/5.0",
        )

        assert response.status_code == 400

    def test_non_healthcheck_path_with_elb_user_agent_and_ip_host_is_blocked(self, client):
        response = client.get(
            "/",
            HTTP_HOST=IP_HOST,
            HTTP_USER_AGENT=ELB_USER_AGENT,
        )

        assert response.status_code == 400

    def test_healthcheck_with_elb_user_agent_and_valid_host_returns_200(self, client):
        response = client.get(
            "/healthcheck/",
            HTTP_HOST="testserver",
            HTTP_USER_AGENT=ELB_USER_AGENT,
        )

        assert response.status_code == 200

    def test_elb_healthcheck_with_ip_host_and_port_returns_200(self, client):
        response = client.get(
            "/healthcheck/",
            HTTP_HOST=f"{IP_HOST}:8000",
            HTTP_USER_AGENT=ELB_USER_AGENT,
        )

        assert response.status_code == 200
        assert response.content == b"OK"

    def test_elb_healthcheck_with_ipv6_host_returns_200(self, client):
        response = client.get(
            "/healthcheck/",
            HTTP_HOST="[2001:db8::1]:8000",
            HTTP_USER_AGENT=ELB_USER_AGENT,
        )

        assert response.status_code == 200
        assert response.content == b"OK"
