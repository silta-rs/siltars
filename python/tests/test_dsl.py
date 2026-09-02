import unittest

from silta import App


class AppRouteValidationTests(unittest.TestCase):
    def test_rejects_unclosed_route_parameter(self) -> None:
        app = App()

        with self.assertRaisesRegex(ValueError, "complete path segments"):
            app.get("/a/{unclosed")

    def test_accepts_complete_route_parameter(self) -> None:
        app = App()

        @app.get("/a/{item_id}")
        def handler() -> dict[str, bool]:
            return {"ok": True}

        self.assertEqual(app.routes[0].path, "/a/{item_id}")

    def test_rejects_non_ascii_route_parameter(self) -> None:
        app = App()

        with self.assertRaisesRegex(ValueError, "valid identifiers"):
            app.get("/a/{ид}")


if __name__ == "__main__":
    unittest.main()
