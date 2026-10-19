# Contributing

Fork the repository and follow the [quick start](README.md#quick-start). Use your own
API key and keep credentials, photos, and evaluation artifacts out of pull requests.
The [development guide](docs/development.md) explains services, tests, and evaluation.

Keep each pull request focused. Explain the problem, the change, and how you checked
it. Update the relevant tool guide when behavior or limitations change. For Find
experiments, preserve V4 as the control and follow the
[evaluation workflow](docs/development.md#changing-detection-or-evaluation-settings).
Mocked tests verify software behavior; accuracy claims need independent reference labels.

Run checks relevant to your change. For frontend changes:

```sh
pnpm test
pnpm build
JEV_UI_TEST_ROOT=dist .venv/bin/python -m unittest tests.test_tool_modules -v
```

These checks make no paid model calls. Live evaluations do. Review publication
candidates using [SECURITY.md](SECURITY.md) before committing or opening a pull request.

[GitHub checks](.github/workflows/checks.yml) run these checks on Python 3.10 and 3.12
for pushes and pull requests, without API credentials or example-dataset downloads.

By submitting a contribution, you agree to license it under this project's
[MIT License](LICENSE). Submit only work you have the right to contribute, and
preserve any third-party copyright and license notices.
