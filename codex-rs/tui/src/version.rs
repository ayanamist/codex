/// The current Codex CLI version as embedded at compile time.
pub const CODEX_CLI_VERSION: &str = if cfg!(test) {
    // Keep snapshot layout and development-version policy independent of Cargo release stamping.
    "0.0.0"
} else {
    env!("CARGO_PKG_VERSION")
};
