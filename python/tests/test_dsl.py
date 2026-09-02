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

    def test_describes_python_handler_route(self) -> None:
        app = App()

        @app.post("/python/echo", python=True)
        def echo() -> dict[str, bool]:
            return {"ok": True}

        route = app.describe()["routes"][0]
        self.assertEqual(route["method"], "POST")
        self.assertEqual(route["path"], "/python/echo")
        self.assertTrue(route["handler"].endswith("echo"))
        self.assertTrue(route["python_handler"])

    def test_rejects_python_handler_with_native_response(self) -> None:
        app = App()

        with self.assertRaisesRegex(ValueError, "python routes"):
            app.get("/hello", response={"hello": "world"}, python=True)


if __name__ == "__main__":
    unittest.main()
