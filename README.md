<p align="center"><strong>Codex CLI — ayanamist fork</strong>, based on OpenAI's coding agent that runs locally on your computer.</p>

This repository distributes the `ayanamist/codex` fork. Install it from this
fork's GitHub Releases using the commands below. See the [fork notes](./docs/fork/README.md)
for changes and release details.

<p align="center">
  <img src="https://github.com/openai/codex/blob/main/.github/codex-cli-splash.png" alt="Codex CLI splash" width="80%" />
</p>
</br>
<p>For OpenAI's official products: if you want Codex in your code editor (VS Code, Cursor, Windsurf), <a href="https://developers.openai.com/codex/ide">install in your IDE.</a>
</br>If you want the desktop app experience, run <code>codex app</code> or visit <a href="https://chatgpt.com/codex?app-landing-page=true">the Codex App page</a>.
</br>If you are looking for the <em>cloud-based agent</em> from OpenAI, <strong>Codex Web</strong>, go to <a href="https://chatgpt.com/codex">chatgpt.com/codex</a>.</p>

---

## Quickstart

### Installing and running this fork

On macOS (Apple Silicon) or Linux (x86_64, glibc 2.38+):

```shell
curl -fsSL https://github.com/ayanamist/codex/releases/latest/download/install.sh | sh
```

On Windows (x64), run in PowerShell:

```shell
powershell -ExecutionPolicy ByPass -c "irm https://github.com/ayanamist/codex/releases/latest/download/install.ps1 | iex"
```

The installers download and verify packages from
[this fork's GitHub Releases](https://github.com/ayanamist/codex/releases/latest).
The current release targets are Linux x86_64, macOS ARM64, and Windows x64.
Linux ARM64, Intel macOS, Windows ARM64, and musl/Alpine packages are not currently published.
The official `chatgpt.com` installers, `npm install -g @openai/codex`, and
`brew install --cask codex` install OpenAI's distribution.

Open a new terminal after installation, then verify the version and start Codex:

```shell
codex --version
codex
```

Current fork versions look like `0.167.0-fork.aeae161d`.
For subsequent updates, run `codex update`. See
[installation details](./docs/install.md) for selecting a release, install paths,
and migrating an existing official installation.

### Using Codex with your ChatGPT plan

Run `codex` and select **Sign in with ChatGPT**. We recommend signing into your ChatGPT account to use Codex as part of your Plus, Pro, Business, Edu, or Enterprise plan. [Learn more about what's included in your ChatGPT plan](https://help.openai.com/en/articles/11369540-codex-in-chatgpt).

You can also use Codex with an API key, but this requires [additional setup](https://developers.openai.com/codex/auth#sign-in-with-an-api-key).

## Docs

- [**Codex Documentation**](https://developers.openai.com/codex)
- [**Contributing**](./docs/contributing.md)
- [**Installing & building**](./docs/install.md)
- [**Open source fund**](./docs/open-source-fund.md)

This repository is licensed under the [Apache-2.0 License](LICENSE).
