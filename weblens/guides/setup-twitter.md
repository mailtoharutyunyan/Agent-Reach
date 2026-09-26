# Twitter Advanced Features Setup Guide (twitter-cli)

Basic Twitter reading is available for free through Jina Reader, with no setup required.

Advanced features require twitter-cli (@public-clis/twitter-cli):

- Search tweets (`twitter search`)
- Read full tweets and conversation threads (`twitter tweet`, `twitter thread`)
- User timelines (`twitter timeline`)
- Long-form article reading (`twitter article`)

twitter-cli is a free, open-source tool (installed with pipx), but it needs your Twitter account cookies.

## Quick Setup

1. Check whether twitter-cli is installed:

```bash
which twitter && echo "installed" || echo "not installed"
```

2. Install twitter-cli:

```bash
pipx install twitter-cli
```

3. Confirm the command is installed (no authenticated request is made at this point):

```bash
twitter --help
```

## Getting Cookies (Cookie-Editor method, recommended)

1. Install the [Cookie-Editor](https://cookie-editor.com/) browser extension
2. Log in to x.com
3. Click the Cookie-Editor icon → Export → Header String
4. Run the configure command:

```bash
weblens configure twitter-cookies
```

This extracts `auth_token` and `ct0` and saves them securely to
`~/.weblens/config.yaml`, so `weblens doctor` can check whether the explicit credentials are complete.
`doctor` does not run `twitter status`, does not verify in real time whether the account works, and does not modify the current shell.

By default it only writes `~/.weblens/config.yaml`. Only when the user explicitly agrees to copy the credentials and explicitly adds
`--sync-legacy-twitter` does it additionally write:

- `~/.config/xfetch/session.json`
- `~/.config/bird/credentials.env`

```bash
weblens configure twitter-cookies --sync-legacy-twitter
```

`weblens uninstall` only reminds you about these legacy copies; it does not delete them automatically. To clean them up,
first get the user's confirmation, then delete the two files above manually.

`twitter` is a standalone upstream command and does not read WebLens's config file. When running
`twitter status/search/read/...` directly, you must explicitly set `TWITTER_AUTH_TOKEN` and `TWITTER_CT0`
in the current shell or subprocess environment as described in the next section. Do not rely on automatically reading browser cookies.

## Setting Cookies Manually

If you already know your `auth_token` and `ct0`:

1. Install twitter-cli (if not installed): `pipx install twitter-cli`

2. Set the environment variables:

```bash
export TWITTER_AUTH_TOKEN="your_auth_token"
export TWITTER_CT0="your_ct0"
```

3. Test:

```bash
twitter search "test" -n 1
```

## Proxy Configuration

> twitter-cli supports setting a proxy via environment variables:

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

You can also use a global proxy tool:

```bash
proxychains twitter search "test" -n 1
```

## Fallback: bird CLI

If you have already installed [bird CLI](https://www.npmjs.com/package/@steipete/bird) (`npm install -g @steipete/bird`), it works fine too. WebLens automatically detects and uses an installed bird. The two offer similar features; twitter-cli is the currently recommended option.
