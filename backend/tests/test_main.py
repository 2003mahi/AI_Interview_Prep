import unittest
from fastapi.testclient import TestClient
from app.auth import create_access_token
from app.main import app


class TestHealthAndApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.token = create_access_token(user_id="test-user-123", email="tester@example.com")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data.get("status"), ["ok", "healthy"])

    def test_interview_generation(self):
        payload = {
            "role": "Frontend Engineer",
            "experience_years": 3,
            "topics": ["React", "TypeScript", "Performance"],
        }
        response = self.client.post("/api/v1/interview", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("role"), "Frontend Engineer")
        self.assertEqual(data.get("user_id"), "test-user-123")
        self.assertTrue(len(data.get("questions", [])) > 0)

    def test_interview_invalid_experience(self):
        payload = {
            "role": "Backend Engineer",
            "experience_years": -1,
            "topics": ["Python"],
        }
        response = self.client.post("/api/v1/interview", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
